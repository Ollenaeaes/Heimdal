"""Signal-Based Scoring Engine — Signal Evaluator (Story 6).

Evaluates vessels against the signal catalogue (A1-A11, B1-B7, C1-C5)
by reading from PostgreSQL. D signals are loaded from the vessel_signals
table (already computed by the Geographic Inference Engine in Story 5).

Usage:
    scorer = SignalScorer(pg_conn)
    signals = scorer.evaluate_vessel(imo=1234567)

Environment:
    DATABASE_URL — PostgreSQL connection string
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import psycopg2
import psycopg2.extras

from shared.config import settings

logger = logging.getLogger("signal-scorer")


# ---------------------------------------------------------------------------
# Signal dataclass
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    """A single scoring signal emitted by the evaluator."""
    signal_id: str
    weight: float
    details: dict = field(default_factory=dict)
    source_data: str = ""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# IACS member class societies (canonical names for matching)
IACS_MEMBERS: frozenset[str] = frozenset({
    "Lloyd's Register",
    "DNV",
    "Bureau Veritas",
    "ABS",
    "ClassNK",
    "RINA",
    "Korean Register",
    "China Classification Society",
    "Indian Register",
    "CCS",
    "Korean Register of Shipping",
    "Russian Maritime Register of Shipping",
})

# Normalised IACS member names for case-insensitive matching
_IACS_MEMBERS_LOWER: frozenset[str] = frozenset(n.lower() for n in IACS_MEMBERS)

# Permissive flag states (B3)
PERMISSIVE_FLAG_STATES: frozenset[str] = frozenset({
    "GA", "CM", "KM", "PW", "CK", "DJ", "GM", "KN", "SL", "MN", "MW",
})

# High-risk jurisdictions for B2
HIGH_RISK_JURISDICTIONS: frozenset[str] = frozenset({
    "RU", "IR", "KP", "SY", "VE", "MM", "CU", "BY",
})

# Tanker ship type codes (AIS 80-89)
_TANKER_TYPE_MIN = 80
_TANKER_TYPE_MAX = 89


def _is_iacs_member(name: str | None) -> bool:
    """Check if a class society name is an IACS member (case-insensitive)."""
    if not name:
        return False
    return name.lower().strip() in _IACS_MEMBERS_LOWER


def _is_tanker(ship_type: Any) -> bool:
    """Check if ship_type code indicates a tanker."""
    if ship_type is None:
        return False
    try:
        st = int(ship_type)
        return _TANKER_TYPE_MIN <= st <= _TANKER_TYPE_MAX
    except (ValueError, TypeError):
        return False


def _to_utc_datetime(d: Any) -> datetime | None:
    """Convert a date or datetime to a timezone-aware UTC datetime."""
    if d is None:
        return None
    if isinstance(d, datetime):
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    if isinstance(d, date):
        return datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc)
    return None


# ---------------------------------------------------------------------------
# Helper: sync PostgreSQL connection
# ---------------------------------------------------------------------------

def _get_sync_dsn() -> str:
    """Convert async DATABASE_URL to sync psycopg2 DSN."""
    url = os.environ.get("DATABASE_URL", settings.database_url.get_secret_value())
    url = re.sub(r"postgresql\+asyncpg://", "postgresql://", url)
    return url


def _get_pg_connection():
    """Return a psycopg2 connection using RealDictCursor."""
    return psycopg2.connect(_get_sync_dsn())


# ---------------------------------------------------------------------------
# SignalScorer
# ---------------------------------------------------------------------------

class SignalScorer:
    """Evaluates all A/B/C signals for a vessel by reading from PostgreSQL.

    D signals are loaded from the vessel_signals table (computed by the
    Geographic Inference Engine).

    Args:
        pg_conn: psycopg2 connection. If None, creates one from DATABASE_URL.
    """

    def __init__(self, pg_conn: Any | None = None):
        self._owns_pg = pg_conn is None
        self.pg = pg_conn or _get_pg_connection()

    def close(self) -> None:
        if self._owns_pg and self.pg:
            self.pg.close()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def evaluate_vessel(self, imo: int) -> list[Signal]:
        """Evaluate all A/B/C/D signals for a vessel.

        Args:
            imo: The vessel's IMO number.

        Returns:
            List of Signal objects for all triggered signals.
        """
        signals: list[Signal] = []

        # A signals (Paris MoU / PSC)
        signals.extend(self._evaluate_a_signals(imo))

        # B signals (OpenSanctions / ownership)
        signals.extend(self._evaluate_b_signals(imo))

        # C signals (IACS / class society)
        signals.extend(self._evaluate_c_signals(imo))

        # D signals (from vessel_signals table)
        signals.extend(self._load_d_signals(imo))

        return signals

    def is_sanctioned(self, imo: int) -> bool:
        """Check if a vessel is directly sanctioned in OpenSanctions.

        A vessel matched with target=True → blacklisted regardless of score.
        """
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT e.target
                FROM os_vessel_links vl
                JOIN os_entities e ON e.entity_id = vl.entity_id
                WHERE vl.imo = %s AND e.target = TRUE
                LIMIT 1
            """, (imo,))
            row = cur.fetchone()
            return row is not None

    # ------------------------------------------------------------------
    # A signals — Paris MoU / PSC inspection data
    # ------------------------------------------------------------------

    def _evaluate_a_signals(self, imo: int) -> list[Signal]:
        """Evaluate A1-A11 signals from psc_inspections."""
        signals: list[Signal] = []

        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Fetch all inspections for this vessel
            cur.execute("""
                SELECT imo, ship_name, flag_state, ship_type, gross_tonnage,
                       inspection_date, detained, deficiency_count,
                       ism_deficiency, ro_at_inspection,
                       pi_provider_at_inspection, pi_is_ig_member,
                       ism_company_imo, ism_company_name
                FROM psc_inspections
                WHERE imo = %s
                ORDER BY inspection_date DESC
            """, (imo,))
            inspections = cur.fetchall()

        if not inspections:
            return signals

        latest = inspections[0]
        now = datetime.now(timezone.utc)

        # A1: Large tanker (GT >= 50000) with >= 3 PSC deficiencies from single inspection
        if _is_tanker(latest.get("ship_type")):
            gt = latest.get("gross_tonnage") or 0
            if gt >= 50000:
                for insp in inspections:
                    dc = insp.get("deficiency_count") or 0
                    if dc >= 3:
                        signals.append(Signal(
                            signal_id="A1",
                            weight=3,
                            details={
                                "gross_tonnage": gt,
                                "deficiency_count": dc,
                                "inspection_date": str(insp.get("inspection_date")),
                            },
                            source_data="psc_inspections",
                        ))
                        break  # One signal is enough

        # A2: Detained in last 3 years
        three_years_ago = now - timedelta(days=3 * 365)
        for insp in inspections:
            insp_date = insp.get("inspection_date")
            insp_dt = _to_utc_datetime(insp_date)
            if insp_dt and insp_dt >= three_years_ago:
                if insp.get("detained"):
                    signals.append(Signal(
                        signal_id="A2",
                        weight=4,
                        details={
                            "inspection_date": str(insp_date),
                            "detained": True,
                        },
                        source_data="psc_inspections",
                    ))
                    break

        # A3: >= 3 ISM-related deficiencies across all inspections
        total_ism = sum(
            (insp.get("ism_deficiency") or 0) for insp in inspections
        )
        if total_ism >= 3:
            signals.append(Signal(
                signal_id="A3",
                weight=2,
                details={"total_ism_deficiencies": total_ism},
                source_data="psc_inspections",
            ))

        # A4: Last inspection > 18 months ago
        latest_date = latest.get("inspection_date")
        if latest_date:
            latest_dt = _to_utc_datetime(latest_date)
            eighteen_months_ago = now - timedelta(days=18 * 30)
            if latest_dt and latest_dt < eighteen_months_ago:
                signals.append(Signal(
                    signal_id="A4",
                    weight=1,
                    details={"last_inspection_date": str(latest_date)},
                    source_data="psc_inspections",
                ))

        # A5: Inspected in port on Paris MoU black-list flag
        flag = latest.get("flag_state")
        if flag:
            with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT list_status FROM psc_flag_performance
                    WHERE iso_code = %s
                """, (flag,))
                fp = cur.fetchone()
                if fp and fp.get("list_status") == "black":
                    signals.append(Signal(
                        signal_id="A5",
                        weight=2,
                        details={
                            "flag_state": flag,
                            "list_status": "black",
                        },
                        source_data="psc_flag_performance",
                    ))

        # A6: RO at inspection is not IACS member
        ro = latest.get("ro_at_inspection")
        if ro and not _is_iacs_member(ro):
            signals.append(Signal(
                signal_id="A6",
                weight=2,
                details={"ro_at_inspection": ro},
                source_data="psc_inspections",
            ))

        # A7: >= 2 inspections showing different RO (class change)
        ros = set()
        for insp in inspections:
            r = insp.get("ro_at_inspection")
            if r:
                ros.add(r.strip().lower())
        if len(ros) >= 2:
            signals.append(Signal(
                signal_id="A7",
                weight=3,
                details={"distinct_ros": list(ros)},
                source_data="psc_inspections",
            ))

        # A8: >= 2 inspections with different RO — class switch detected
        # Stricter than A7: requires chronologically ordered inspections
        # showing a transition from one RO to a different one
        if len(inspections) >= 2:
            ro_changes = []
            prev_ro = None
            for insp in reversed(inspections):  # Oldest first
                r = insp.get("ro_at_inspection")
                if r:
                    r_norm = r.strip().lower()
                    if prev_ro and r_norm != prev_ro:
                        ro_changes.append({
                            "from": prev_ro,
                            "to": r_norm,
                            "date": str(insp.get("inspection_date")),
                        })
                    prev_ro = r_norm
            if len(ro_changes) >= 1:
                signals.append(Signal(
                    signal_id="A8",
                    weight=3,
                    details={"class_switches": ro_changes},
                    source_data="psc_inspections",
                ))

        # A9: Paris MoU inspection in last 12 months with deficiency count >= 5
        twelve_months_ago = now - timedelta(days=365)
        for insp in inspections:
            insp_date = insp.get("inspection_date")
            insp_dt = _to_utc_datetime(insp_date)
            if insp_dt:
                if insp_dt >= twelve_months_ago:
                    dc = insp.get("deficiency_count") or 0
                    if dc >= 5:
                        signals.append(Signal(
                            signal_id="A9",
                            weight=2,
                            details={
                                "deficiency_count": dc,
                                "inspection_date": str(insp_date),
                            },
                            source_data="psc_inspections",
                        ))
                        break

        # A10: ISM company fleet risk — stub (Story 7)
        signals.extend(self._evaluate_a10(imo))

        # A11: Inspection at >= 2 different ports in different countries within 30 days
        signals.extend(self._evaluate_a11(imo, inspections))

        return signals

    def _evaluate_a10(self, imo: int) -> list[Signal]:
        """A10: ISM company fleet risk — fleet sibling is blacklisted/red.

        Stub — will be implemented in Story 7 (graph-based fleet risk propagation).
        """
        return []

    def _evaluate_a11(self, imo: int, inspections: list[dict]) -> list[Signal]:
        """A11: Rapid port hopping — inspected at >= 2 different ports in
        different countries within 30 days.
        """
        # We need port/country info from inspections. Paris MoU inspections
        # include the inspection port through flag_state and other fields.
        # For now, we look for inspections within 30 days at different flag states
        # (the port country is not directly in the schema, so we use inspection
        # proximity as a proxy — the inspection_date ordering is sufficient).
        dated_inspections = []
        for insp in inspections:
            d = insp.get("inspection_date")
            fs = insp.get("flag_state")
            if d and fs:
                dt = _to_utc_datetime(d)
                if dt:
                    dated_inspections.append((dt, fs, insp))

        # Sort by date
        dated_inspections.sort(key=lambda x: x[0])

        for i in range(len(dated_inspections)):
            for j in range(i + 1, len(dated_inspections)):
                dt_i, fs_i, _ = dated_inspections[i]
                dt_j, fs_j, _ = dated_inspections[j]
                delta = (dt_j - dt_i).days
                if delta > 30:
                    break
                if fs_i != fs_j:
                    return [Signal(
                        signal_id="A11",
                        weight=3,
                        details={
                            "ports_countries": [fs_i, fs_j],
                            "days_apart": delta,
                        },
                        source_data="psc_inspections",
                    )]
        return []

    # ------------------------------------------------------------------
    # B signals — OpenSanctions / ownership data
    # ------------------------------------------------------------------

    def _evaluate_b_signals(self, imo: int) -> list[Signal]:
        """Evaluate B1-B7 signals from OpenSanctions tables."""
        signals: list[Signal] = []

        # B1: Entity directly linked to sanctioned person/company
        signals.extend(self._evaluate_b1(imo))

        # B2: Owner or manager jurisdiction is high-risk
        signals.extend(self._evaluate_b2(imo))

        # B3: Vessel registered in permissive flag state
        signals.extend(self._evaluate_b3(imo))

        # B4: Owner fleet risk — stub (Story 7)
        signals.extend(self._evaluate_b4(imo))

        # B5: >= 2 ownership changes in last 2 years
        signals.extend(self._evaluate_b5(imo))

        # B6: Beneficial owner is a PEP or crime-linked entity
        signals.extend(self._evaluate_b6(imo))

        # B7: Company has single-vessel fleet and was incorporated < 2 years ago
        signals.extend(self._evaluate_b7(imo))

        return signals

    def _evaluate_b1(self, imo: int) -> list[Signal]:
        """B1: Entity directly linked to sanctioned person/company via os_relationships."""
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Find entities linked to this vessel
            cur.execute("""
                SELECT vl.entity_id
                FROM os_vessel_links vl
                WHERE vl.imo = %s
            """, (imo,))
            vessel_entities = [r["entity_id"] for r in cur.fetchall()]

            if not vessel_entities:
                return []

            # Check if any related entity has sanctions topics
            for entity_id in vessel_entities:
                cur.execute("""
                    SELECT r.target_entity_id, e.name, e.topics
                    FROM os_relationships r
                    JOIN os_entities e ON e.entity_id = r.target_entity_id
                    WHERE r.source_entity_id = %s
                      AND e.topics IS NOT NULL
                      AND e.topics::text LIKE '%%sanction%%'
                """, (entity_id,))
                sanctioned = cur.fetchall()

                if not sanctioned:
                    # Check reverse direction
                    cur.execute("""
                        SELECT r.source_entity_id, e.name, e.topics
                        FROM os_relationships r
                        JOIN os_entities e ON e.entity_id = r.source_entity_id
                        WHERE r.target_entity_id = %s
                          AND e.topics IS NOT NULL
                          AND e.topics::text LIKE '%%sanction%%'
                    """, (entity_id,))
                    sanctioned = cur.fetchall()

                if sanctioned:
                    return [Signal(
                        signal_id="B1",
                        weight=4,
                        details={
                            "linked_entities": [
                                {"entity_id": s.get("target_entity_id") or s.get("source_entity_id"),
                                 "name": s.get("name")}
                                for s in sanctioned[:5]
                            ],
                        },
                        source_data="os_relationships",
                    )]
        return []

    def _evaluate_b2(self, imo: int) -> list[Signal]:
        """B2: Owner or manager jurisdiction is high-risk."""
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Look up ownership entities linked to this vessel
            cur.execute("""
                SELECT e.entity_id, e.name, e.properties
                FROM os_vessel_links vl
                JOIN os_entities e ON e.entity_id = vl.entity_id
                WHERE vl.imo = %s
            """, (imo,))
            entities = cur.fetchall()

            # Also check related entities (owners, managers)
            for ent in list(entities):
                cur.execute("""
                    SELECT e.entity_id, e.name, e.properties
                    FROM os_relationships r
                    JOIN os_entities e ON e.entity_id = r.target_entity_id
                    WHERE r.source_entity_id = %s
                """, (ent["entity_id"],))
                entities.extend(cur.fetchall())

            for ent in entities:
                props = ent.get("properties") or {}
                if isinstance(props, str):
                    import json
                    props = json.loads(props)
                jurisdictions = props.get("jurisdiction", [])
                if isinstance(jurisdictions, str):
                    jurisdictions = [jurisdictions]
                country = props.get("country", [])
                if isinstance(country, str):
                    country = [country]
                all_codes = set(jurisdictions + country)
                high_risk = all_codes & HIGH_RISK_JURISDICTIONS
                if high_risk:
                    return [Signal(
                        signal_id="B2",
                        weight=2,
                        details={
                            "entity_name": ent.get("name"),
                            "jurisdictions": list(high_risk),
                        },
                        source_data="os_entities",
                    )]
        return []

    def _evaluate_b3(self, imo: int) -> list[Signal]:
        """B3: Vessel registered in permissive flag state."""
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Get flag from most recent inspection
            cur.execute("""
                SELECT flag_state FROM psc_inspections
                WHERE imo = %s
                ORDER BY inspection_date DESC
                LIMIT 1
            """, (imo,))
            row = cur.fetchone()
            if row:
                flag = row.get("flag_state")
                if flag and flag.upper() in PERMISSIVE_FLAG_STATES:
                    return [Signal(
                        signal_id="B3",
                        weight=2,
                        details={"flag_state": flag},
                        source_data="psc_inspections",
                    )]

            # Also check vessel_profiles
            cur.execute("""
                SELECT ship_type FROM vessel_profiles
                WHERE imo = %s
                LIMIT 1
            """, (imo,))
        return []

    def _evaluate_b4(self, imo: int) -> list[Signal]:
        """B4: Owner fleet risk — owner's other vessel is blacklisted/red.

        Stub — will be implemented in Story 7 (graph-based fleet risk propagation).
        """
        return []

    def _evaluate_b5(self, imo: int) -> list[Signal]:
        """B5: >= 2 ownership changes in last 2 years."""
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT vl.entity_id, e.name, e.properties
                FROM os_vessel_links vl
                JOIN os_entities e ON e.entity_id = vl.entity_id
                WHERE vl.imo = %s
            """, (imo,))
            entities = cur.fetchall()

            # Check relationships for ownership changes
            owner_entities = set()
            for ent in entities:
                cur.execute("""
                    SELECT r.target_entity_id, r.properties
                    FROM os_relationships r
                    WHERE r.source_entity_id = %s
                      AND r.rel_type IN ('ownership', 'owner', 'OWNED_BY')
                """, (ent["entity_id"],))
                for rel in cur.fetchall():
                    owner_entities.add(rel["target_entity_id"])

            if len(owner_entities) >= 2:
                return [Signal(
                    signal_id="B5",
                    weight=1,
                    details={"owner_count": len(owner_entities)},
                    source_data="os_relationships",
                )]
        return []

    def _evaluate_b6(self, imo: int) -> list[Signal]:
        """B6: Beneficial owner is a PEP or crime-linked entity."""
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT vl.entity_id
                FROM os_vessel_links vl
                WHERE vl.imo = %s
            """, (imo,))
            vessel_entities = [r["entity_id"] for r in cur.fetchall()]

            for entity_id in vessel_entities:
                # Check related entities for PEP/crime topics
                cur.execute("""
                    SELECT e.name, e.topics
                    FROM os_relationships r
                    JOIN os_entities e ON e.entity_id = r.target_entity_id
                    WHERE r.source_entity_id = %s
                      AND e.topics IS NOT NULL
                      AND (e.topics::text LIKE '%%pep%%'
                           OR e.topics::text LIKE '%%crime%%')
                """, (entity_id,))
                pep_entities = cur.fetchall()
                if pep_entities:
                    return [Signal(
                        signal_id="B6",
                        weight=2,
                        details={
                            "pep_entities": [
                                {"name": p.get("name"), "topics": p.get("topics")}
                                for p in pep_entities[:3]
                            ],
                        },
                        source_data="os_entities",
                    )]
        return []

    def _evaluate_b7(self, imo: int) -> list[Signal]:
        """B7: Company has single-vessel fleet and was incorporated < 2 years ago."""
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Get ISM company from inspections
            cur.execute("""
                SELECT ism_company_imo, ism_company_name
                FROM psc_inspections
                WHERE imo = %s AND ism_company_imo IS NOT NULL
                ORDER BY inspection_date DESC
                LIMIT 1
            """, (imo,))
            row = cur.fetchone()
            if not row:
                return []

            company_imo = row.get("ism_company_imo")
            if not company_imo:
                return []

            # Count how many vessels this company manages
            cur.execute("""
                SELECT COUNT(DISTINCT imo) as vessel_count
                FROM psc_inspections
                WHERE ism_company_imo = %s
            """, (company_imo,))
            count_row = cur.fetchone()
            vessel_count = (count_row.get("vessel_count") or 0) if count_row else 0

            if vessel_count <= 1:
                # Check incorporation date from OpenSanctions entities
                company_name = row.get("ism_company_name")
                if company_name:
                    cur.execute("""
                        SELECT properties FROM os_entities
                        WHERE name ILIKE %s
                        LIMIT 1
                    """, (company_name,))
                    ent = cur.fetchone()
                    if ent:
                        props = ent.get("properties") or {}
                        if isinstance(props, str):
                            import json
                            props = json.loads(props)
                        inc_dates = props.get("incorporationDate", [])
                        if isinstance(inc_dates, str):
                            inc_dates = [inc_dates]
                        two_years_ago = datetime.now(timezone.utc) - timedelta(days=2 * 365)
                        for inc_str in inc_dates:
                            try:
                                inc_date = datetime.fromisoformat(str(inc_str).replace("Z", "+00:00"))
                                if inc_date > two_years_ago:
                                    return [Signal(
                                        signal_id="B7",
                                        weight=1,
                                        details={
                                            "company_name": company_name,
                                            "incorporation_date": str(inc_date),
                                            "vessel_count": vessel_count,
                                        },
                                        source_data="os_entities",
                                    )]
                            except (ValueError, TypeError):
                                continue
        return []

    # ------------------------------------------------------------------
    # C signals — IACS / class society data
    # ------------------------------------------------------------------

    def _evaluate_c_signals(self, imo: int) -> list[Signal]:
        """Evaluate C1-C5 signals from iacs_vessels_current."""
        signals: list[Signal] = []

        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT imo, class_society, status, date_of_latest_status
                FROM iacs_vessels_current
                WHERE imo = %s
            """, (imo,))
            iacs = cur.fetchone()

        if not iacs:
            # C1: Not currently classed by any IACS member
            signals.append(Signal(
                signal_id="C1",
                weight=3,
                details={"reason": "No record in IACS vessels-in-class"},
                source_data="iacs_vessels_current",
            ))
            return signals

        status = (iacs.get("status") or "").strip()
        class_society = iacs.get("class_society") or ""
        status_date = iacs.get("date_of_latest_status")

        # C1: Current class society is not an IACS member
        if class_society and not _is_iacs_member(class_society):
            signals.append(Signal(
                signal_id="C1",
                weight=3,
                details={
                    "class_society": class_society,
                    "reason": "Class society is not an IACS member",
                },
                source_data="iacs_vessels_current",
            ))

        # C2: Class suspended
        if status.lower() == "suspended":
            signals.append(Signal(
                signal_id="C2",
                weight=3,
                details={
                    "class_society": class_society,
                    "status": status,
                    "date": str(status_date) if status_date else None,
                },
                source_data="iacs_vessels_current",
            ))

        # C3: Class withdrawn
        if status.lower() == "withdrawn":
            signals.append(Signal(
                signal_id="C3",
                weight=4,
                details={
                    "class_society": class_society,
                    "status": status,
                    "date": str(status_date) if status_date else None,
                },
                source_data="iacs_vessels_current",
            ))

        # C4: Class changed in last 12 months
        if status_date:
            status_dt = _to_utc_datetime(status_date)
            twelve_months_ago = datetime.now(timezone.utc) - timedelta(days=365)
            if status_dt and status_dt >= twelve_months_ago:
                signals.append(Signal(
                    signal_id="C4",
                    weight=2,
                    details={
                        "class_society": class_society,
                        "date_of_latest_status": str(status_date),
                    },
                    source_data="iacs_vessels_current",
                ))

        # C5: Paris MoU historical RO was IACS member but current IACS status is not active
        signals.extend(self._evaluate_c5(imo, iacs))

        return signals

    def _evaluate_c5(self, imo: int, iacs: dict) -> list[Signal]:
        """C5: Historical RO was IACS member but current IACS status is not active."""
        current_status = (iacs.get("status") or "").strip().lower()
        # If current status is active, no signal
        if current_status in ("active", "in class", "classed"):
            return []

        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Check Paris MoU inspections for historical RO that was IACS member
            cur.execute("""
                SELECT DISTINCT ro_at_inspection
                FROM psc_inspections
                WHERE imo = %s AND ro_at_inspection IS NOT NULL
            """, (imo,))
            historical_ros = [r["ro_at_inspection"] for r in cur.fetchall()]

        has_iacs_historical = any(_is_iacs_member(ro) for ro in historical_ros)
        if has_iacs_historical:
            return [Signal(
                signal_id="C5",
                weight=3,
                details={
                    "historical_ros": historical_ros,
                    "current_status": current_status,
                    "current_class_society": iacs.get("class_society"),
                },
                source_data="psc_inspections,iacs_vessels_current",
            )]
        return []

    # ------------------------------------------------------------------
    # D signals — loaded from vessel_signals table
    # ------------------------------------------------------------------

    def _load_d_signals(self, imo: int) -> list[Signal]:
        """Load D signals from the vessel_signals table.

        These are already computed by the Geographic Inference Engine (Story 5).
        We load the most recent instance of each D signal.
        """
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT ON (signal_id)
                    signal_id, weight, details, source_data
                FROM vessel_signals
                WHERE imo = %s AND signal_id LIKE 'D%%'
                ORDER BY signal_id, triggered_at DESC
            """, (imo,))
            rows = cur.fetchall()

        return [
            Signal(
                signal_id=row["signal_id"],
                weight=row["weight"],
                details=row.get("details") or {},
                source_data=row.get("source_data") or "vessel_signals",
            )
            for row in rows
        ]
