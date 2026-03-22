"""IACS Vessels-in-Class tracker.

Downloads the weekly IACS CSV, diffs against previous state in PostgreSQL,
and logs all changes to a change history table.  Provides query functions
for Heimdal's enrichment pipeline.

Usage:
    # Auto-discover latest file from IACS website
    python iacs_tracker.py

    # Import a specific URL
    python iacs_tracker.py --url https://iacs.s3.af-south-1.amazonaws.com/.../EquasisToIACS_20260320_949.zip

    # Import a local file (e.g. manually downloaded)
    python iacs_tracker.py --file /tmp/EquasisToIACS_20260320_949.zip

    # Bootstrap: import all 3 available files oldest-first
    python iacs_tracker.py --bootstrap

    # Query a single vessel
    python iacs_tracker.py --check-vessel 9123456
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import logging
import os
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("iacs-tracker")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IACS_PAGE_URL = "https://iacs.org.uk/membership/vessels-in-class/"

# CSV column names (semicolon-delimited) — mapped flexibly
EXPECTED_COLUMNS = {
    "imo": ["imo", "imo number", "imo_number"],
    "ship_name": ["ship name", "ship_name", "name"],
    "class_society": ["class", "class_society", "classification society"],
    "date_of_survey": ["date of survey", "date_of_survey", "survey date"],
    "date_of_next_survey": ["date of next survey", "date_of_next_survey"],
    "date_of_latest_status": ["date of latest status", "date_of_latest_status"],
    "status": ["status"],
    "reason": ["reason for the status", "reason_for_the_status", "reason"],
}

# IACS CSV class codes → standard abbreviations used in Heimdal
IACS_CLASS_MAP: dict[str, str] = {
    "ABS": "ABS",
    "BV": "BV",
    "CCS": "CCS",
    "CRS": "CRS",
    "IRS": "IRS",
    "KR": "KR",
    "LRS": "LR",   # Lloyd's Register
    "NKK": "NK",   # Nippon Kaiji Kyokai (ClassNK)
    "NV": "DNV",   # Det Norske Veritas
    "PRS": "PRS",
    "RINA": "RINA",
    "TLV": "TLV",  # Türk Loydu — not IACS member
}

# High-risk status values
HIGH_RISK_STATUSES = {"Withdrawn", "Suspended"}

# High-risk change types
HIGH_RISK_CHANGE_TYPES = {"status_change", "class_change", "name_change", "vessel_removed"}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class IACSEntry:
    """A single row from the IACS CSV."""
    imo: int
    ship_name: str
    class_society: str
    date_of_survey: date | None
    date_of_next_survey: date | None
    date_of_latest_status: date | None
    status: str
    reason: str

    def row_hash(self) -> str:
        """Hash of mutable fields for change detection."""
        parts = [
            self.ship_name,
            self.class_society,
            str(self.date_of_survey or ""),
            str(self.date_of_next_survey or ""),
            str(self.date_of_latest_status or ""),
            self.status,
            self.reason,
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:
        return {
            "imo": self.imo,
            "ship_name": self.ship_name,
            "class_society": self.class_society,
            "date_of_survey": str(self.date_of_survey) if self.date_of_survey else None,
            "date_of_next_survey": str(self.date_of_next_survey) if self.date_of_next_survey else None,
            "date_of_latest_status": str(self.date_of_latest_status) if self.date_of_latest_status else None,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass
class VesselSummary:
    """Aggregated state for one IMO across all IACS entries."""
    imo: int
    ship_name: str
    class_society: str          # from the "best" entry
    date_of_survey: date | None
    date_of_next_survey: date | None
    date_of_latest_status: date | None
    status: str
    reason: str
    all_entries: list[dict[str, Any]] = field(default_factory=list)

    def row_hash(self) -> str:
        """Hash covering the primary fields + all entries."""
        parts = [
            self.ship_name,
            self.class_society,
            str(self.date_of_survey or ""),
            str(self.date_of_next_survey or ""),
            str(self.date_of_latest_status or ""),
            self.status,
            self.reason,
            str(len(self.all_entries)),
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Scraping & download
# ---------------------------------------------------------------------------

def scrape_download_links() -> list[dict[str, str]]:
    """Scrape the IACS vessels-in-class page for download URLs.

    Returns list of dicts with 'url', 'filename', 'date_str' sorted oldest-first.
    """
    logger.info("Scraping IACS download page: %s", IACS_PAGE_URL)
    resp = requests.get(IACS_PAGE_URL, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "EquasisToIACS" in href and href.endswith(".zip"):
            # Extract date from filename: EquasisToIACS_YYYYMMDD_NNN.zip
            match = re.search(r"EquasisToIACS_(\d{8})_(\d+)\.zip", href)
            if match:
                links.append({
                    "url": href,
                    "filename": f"EquasisToIACS_{match.group(1)}_{match.group(2)}.zip",
                    "date_str": match.group(1),
                    "seq": int(match.group(2)),
                })

    # Sort oldest-first for bootstrap processing
    links.sort(key=lambda x: x["date_str"])
    logger.info("Found %d IACS download links", len(links))
    return links


def download_file(url: str) -> Path:
    """Download a zip file to a temp location. Returns local path.

    Caller is responsible for deleting the file after processing.
    """
    logger.info("Downloading %s", url)
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()

    fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="iacs_")
    try:
        with os.fdopen(fd, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception:
        os.unlink(tmp_path)
        raise

    size_mb = Path(tmp_path).stat().st_size / 1e6
    logger.info("Downloaded %.1f MB to temp file", size_mb)
    return Path(tmp_path)


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> date | None:
    """Parse YYYYMMDD date string, returning None on failure."""
    if not s or not s.strip():
        return None
    s = s.strip()
    try:
        if len(s) == 8:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        # Try ISO format
        return date.fromisoformat(s)
    except (ValueError, IndexError):
        return None


def _clean_ship_name(name: str) -> str:
    """Clean ship name — remove date suffix like '(20/03/26)'."""
    if not name:
        return ""
    # Remove trailing parenthetical date: ASTRALIUM(22/04/25)
    cleaned = re.sub(r"\(\d{2}/\d{2}/\d{2}\)$", "", name).strip()
    return cleaned


def _map_columns(header: list[str]) -> dict[str, int]:
    """Map CSV header to our expected columns. Returns field_name → column_index."""
    mapping = {}
    header_lower = [h.strip().lower() for h in header]

    for field_name, candidates in EXPECTED_COLUMNS.items():
        for candidate in candidates:
            if candidate in header_lower:
                mapping[field_name] = header_lower.index(candidate)
                break

    missing = set(EXPECTED_COLUMNS.keys()) - set(mapping.keys())
    if missing:
        logger.warning("Missing columns in CSV: %s (header: %s)", missing, header)

    return mapping


def parse_csv(zip_path: Path) -> tuple[list[IACSEntry], str]:
    """Parse IACS CSV from a zip file.

    Returns (entries, file_hash).
    """
    with zipfile.ZipFile(zip_path) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError(f"No CSV file found in {zip_path}")

        csv_name = csv_names[0]
        raw_bytes = zf.read(csv_name)

    # Hash the raw CSV for dedup
    file_hash = hashlib.sha256(raw_bytes).hexdigest()[:32]

    # Parse CSV (semicolon-delimited)
    text = raw_bytes.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter=";")

    rows = list(reader)
    if not rows:
        return [], file_hash

    col_map = _map_columns(rows[0])
    entries = []

    for row_num, row in enumerate(rows[1:], start=2):
        try:
            if len(row) < max(col_map.values()) + 1:
                continue

            imo_str = row[col_map["imo"]].strip()
            if not imo_str or not imo_str.isdigit():
                continue

            imo = int(imo_str)
            if imo < 1000000:
                continue  # Invalid IMO

            entry = IACSEntry(
                imo=imo,
                ship_name=_clean_ship_name(row[col_map.get("ship_name", 1)]),
                class_society=row[col_map.get("class_society", 2)].strip(),
                date_of_survey=_parse_date(row[col_map.get("date_of_survey", 3)]),
                date_of_next_survey=_parse_date(row[col_map.get("date_of_next_survey", 4)]),
                date_of_latest_status=_parse_date(row[col_map.get("date_of_latest_status", 5)]),
                status=row[col_map.get("status", 6)].strip(),
                reason=row[col_map.get("reason", 7)].strip() if len(row) > col_map.get("reason", 7) else "",
            )
            entries.append(entry)
        except (ValueError, IndexError, KeyError) as e:
            if row_num <= 5:
                logger.warning("Parse error at row %d: %s", row_num, e)

    logger.info("Parsed %d entries from %s", len(entries), csv_name)
    return entries, file_hash


def aggregate_by_imo(entries: list[IACSEntry]) -> dict[int, VesselSummary]:
    """Aggregate entries by IMO, picking the best representative row.

    For each IMO, the "best" row is:
    1. The one with the most recent date_of_latest_status
    2. If tied, prefer Delivered/Reinstated over Withdrawn/Suspended
    3. If still tied, prefer IACS member society
    """
    by_imo: dict[int, list[IACSEntry]] = {}
    for e in entries:
        by_imo.setdefault(e.imo, []).append(e)

    status_priority = {"Delivered": 0, "Reinstated": 1, "Reassigned": 2, "Suspended": 3, "Withdrawn": 4}

    summaries = {}
    for imo, imo_entries in by_imo.items():
        # Sort: most recent status date first, then prefer active statuses
        imo_entries.sort(
            key=lambda e: (
                e.date_of_latest_status or date.min,
                -status_priority.get(e.status, 5),
            ),
            reverse=True,
        )

        best = imo_entries[0]

        # If the best entry is Withdrawn/Suspended but there's a more recent
        # Delivered/Reinstated entry from a DIFFERENT society, prefer that
        if best.status in HIGH_RISK_STATUSES:
            for e in imo_entries[1:]:
                if e.status in ("Delivered", "Reinstated") and e.class_society != best.class_society:
                    if e.date_of_latest_status and best.date_of_latest_status:
                        if e.date_of_latest_status >= best.date_of_latest_status:
                            best = e
                            break

        summaries[imo] = VesselSummary(
            imo=imo,
            ship_name=best.ship_name,
            class_society=best.class_society,
            date_of_survey=best.date_of_survey,
            date_of_next_survey=best.date_of_next_survey,
            date_of_latest_status=best.date_of_latest_status,
            status=best.status,
            reason=best.reason,
            all_entries=[e.to_dict() for e in imo_entries],
        )

    return summaries


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

def get_connection() -> psycopg2.extensions.connection:
    """Get a psycopg2 connection from DATABASE_URL."""
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable not set")

    # Strip asyncpg driver prefix if present
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    return psycopg2.connect(db_url)


def is_already_processed(conn, file_hash: str) -> bool:
    """Check if this file has already been imported."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM iacs_snapshots WHERE file_hash = %s", (file_hash,))
        return cur.fetchone() is not None


def load_current_state(conn) -> dict[int, dict[str, Any]]:
    """Load all current IACS vessel records keyed by IMO."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM iacs_vessels_current")
        return {row["imo"]: dict(row) for row in cur.fetchall()}


def diff_and_store(
    conn,
    summaries: dict[int, VesselSummary],
    snapshot_date: date,
    filename: str,
    file_hash: str,
) -> dict[str, int]:
    """Diff new data against current state, store changes, update current.

    Returns change counts.
    """
    current = load_current_state(conn)
    now = datetime.now(timezone.utc)

    changes: list[dict[str, Any]] = []
    added = 0
    changed = 0
    removed = 0

    new_imos = set(summaries.keys())
    old_imos = set(current.keys())

    # --- New vessels ---
    for imo in new_imos - old_imos:
        s = summaries[imo]
        added += 1
        changes.append({
            "imo": imo,
            "ship_name": s.ship_name,
            "change_type": "vessel_added",
            "field_changed": None,
            "old_value": None,
            "new_value": f"class={s.class_society} status={s.status}",
            "is_high_risk": s.status in HIGH_RISK_STATUSES,
            "snapshot_date": snapshot_date,
        })

    # --- Changed vessels ---
    for imo in new_imos & old_imos:
        s = summaries[imo]
        c = current[imo]
        new_hash = s.row_hash()

        if new_hash == c.get("row_hash"):
            continue  # No change

        changed += 1

        # Detect specific field changes
        if s.status != (c.get("status") or ""):
            is_high_risk = (
                s.status in HIGH_RISK_STATUSES
                or c.get("status") in HIGH_RISK_STATUSES
            )
            changes.append({
                "imo": imo,
                "ship_name": s.ship_name,
                "change_type": "status_change",
                "field_changed": "status",
                "old_value": c.get("status"),
                "new_value": s.status,
                "is_high_risk": is_high_risk,
                "snapshot_date": snapshot_date,
            })
            # Also log reason change if status changed
            if s.reason != (c.get("reason") or ""):
                changes.append({
                    "imo": imo,
                    "ship_name": s.ship_name,
                    "change_type": "status_change",
                    "field_changed": "reason",
                    "old_value": c.get("reason"),
                    "new_value": s.reason,
                    "is_high_risk": is_high_risk,
                    "snapshot_date": snapshot_date,
                })

        if s.class_society != (c.get("class_society") or ""):
            # Class society change — high risk if moving away from IACS
            old_is_iacs = (c.get("class_society") or "") in IACS_CLASS_MAP
            new_is_iacs = s.class_society in IACS_CLASS_MAP
            is_downgrade = old_is_iacs and not new_is_iacs
            changes.append({
                "imo": imo,
                "ship_name": s.ship_name,
                "change_type": "class_change",
                "field_changed": "class_society",
                "old_value": c.get("class_society"),
                "new_value": s.class_society,
                "is_high_risk": is_downgrade,
                "snapshot_date": snapshot_date,
            })

        if s.ship_name and c.get("ship_name") and s.ship_name != c["ship_name"]:
            changes.append({
                "imo": imo,
                "ship_name": s.ship_name,
                "change_type": "name_change",
                "field_changed": "ship_name",
                "old_value": c.get("ship_name"),
                "new_value": s.ship_name,
                "is_high_risk": True,
                "snapshot_date": snapshot_date,
            })

        # Survey date updates — routine, not high-risk
        if s.date_of_survey != c.get("date_of_survey"):
            changes.append({
                "imo": imo,
                "ship_name": s.ship_name,
                "change_type": "survey_update",
                "field_changed": "date_of_survey",
                "old_value": str(c.get("date_of_survey") or ""),
                "new_value": str(s.date_of_survey or ""),
                "is_high_risk": False,
                "snapshot_date": snapshot_date,
            })

    # --- Disappeared vessels ---
    for imo in old_imos - new_imos:
        c = current[imo]
        removed += 1
        changes.append({
            "imo": imo,
            "ship_name": c.get("ship_name"),
            "change_type": "vessel_removed",
            "field_changed": None,
            "old_value": f"class={c.get('class_society')} status={c.get('status')}",
            "new_value": None,
            "is_high_risk": True,
            "snapshot_date": snapshot_date,
        })

    # --- Write to database ---
    with conn.cursor() as cur:
        # Insert changes
        if changes:
            psycopg2.extras.execute_batch(
                cur,
                """
                INSERT INTO iacs_vessels_changes
                    (imo, ship_name, change_type, field_changed, old_value, new_value,
                     is_high_risk, detected_at, snapshot_date)
                VALUES
                    (%(imo)s, %(ship_name)s, %(change_type)s, %(field_changed)s,
                     %(old_value)s, %(new_value)s, %(is_high_risk)s, NOW(), %(snapshot_date)s)
                """,
                changes,
                page_size=500,
            )

        # Upsert current state
        import json as _json

        for imo, s in summaries.items():
            cur.execute(
                """
                INSERT INTO iacs_vessels_current
                    (imo, ship_name, class_society, date_of_survey, date_of_next_survey,
                     date_of_latest_status, status, reason, row_hash, all_entries,
                     first_seen, last_seen, snapshot_date)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), %s)
                ON CONFLICT (imo) DO UPDATE SET
                    ship_name = EXCLUDED.ship_name,
                    class_society = EXCLUDED.class_society,
                    date_of_survey = EXCLUDED.date_of_survey,
                    date_of_next_survey = EXCLUDED.date_of_next_survey,
                    date_of_latest_status = EXCLUDED.date_of_latest_status,
                    status = EXCLUDED.status,
                    reason = EXCLUDED.reason,
                    row_hash = EXCLUDED.row_hash,
                    all_entries = EXCLUDED.all_entries,
                    last_seen = NOW(),
                    snapshot_date = EXCLUDED.snapshot_date
                """,
                (
                    imo, s.ship_name, s.class_society,
                    s.date_of_survey, s.date_of_next_survey, s.date_of_latest_status,
                    s.status, s.reason, s.row_hash(),
                    _json.dumps(s.all_entries),
                    snapshot_date,
                ),
            )

        # Mark disappeared vessels (don't delete — just note they're gone)
        if old_imos - new_imos:
            removed_list = list(old_imos - new_imos)
            cur.execute(
                """
                UPDATE iacs_vessels_current
                SET status = 'Removed', reason = 'Disappeared from IACS file',
                    snapshot_date = %s
                WHERE imo = ANY(%s)
                """,
                (snapshot_date, removed_list),
            )

        # Record snapshot
        cur.execute(
            """
            INSERT INTO iacs_snapshots
                (filename, snapshot_date, file_hash, row_count,
                 vessels_added, vessels_changed, vessels_removed)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (filename, snapshot_date, file_hash, len(summaries),
             added, changed, removed),
        )

        # Update vessel_profiles.iacs_data for scoring engine access.
        # Join on IMO — only updates vessels already tracked by Heimdal.
        # Include recent changes (last 90 days) for the scoring rule.
        cur.execute(
            """
            UPDATE vessel_profiles vp
            SET iacs_data = jsonb_build_object(
                'status', ic.status,
                'risk_signal', CASE
                    WHEN ic.status = 'Withdrawn' AND ic.reason ILIKE '%%by society%%' THEN 'critical'
                    WHEN ic.status IN ('Withdrawn', 'Suspended', 'Removed') THEN 'high'
                    WHEN ic.status IN ('Delivered', 'Reinstated') THEN 'none'
                    ELSE 'low'
                END,
                'class_society', ic.class_society,
                'reason', ic.reason,
                'last_seen', ic.last_seen,
                'all_entries', ic.all_entries,
                'snapshot_date', ic.snapshot_date,
                'changes', COALESCE((
                    SELECT jsonb_agg(jsonb_build_object(
                        'change_type', ch.change_type,
                        'field_changed', ch.field_changed,
                        'old_value', ch.old_value,
                        'new_value', ch.new_value,
                        'is_high_risk', ch.is_high_risk,
                        'detected_at', ch.detected_at
                    ) ORDER BY ch.detected_at DESC)
                    FROM iacs_vessels_changes ch
                    WHERE ch.imo = ic.imo
                      AND ch.detected_at >= NOW() - INTERVAL '90 days'
                ), '[]'::jsonb)
            )
            FROM iacs_vessels_current ic
            WHERE vp.imo = ic.imo AND vp.imo IS NOT NULL
            """
        )
        updated_profiles = cur.rowcount
        logger.info("Updated %d vessel_profiles with IACS data", updated_profiles)

        # Also set iacs_data for vessels with IMO that have NO IACS record
        cur.execute(
            """
            UPDATE vessel_profiles vp
            SET iacs_data = jsonb_build_object(
                'status', 'NO_IACS_CLASS',
                'risk_signal', 'moderate',
                'class_society', NULL,
                'reason', 'Vessel not found in any IACS classification society records',
                'last_seen', NULL,
                'all_entries', NULL,
                'snapshot_date', NULL
            )
            WHERE vp.imo IS NOT NULL
              AND vp.imo > 0
              AND NOT EXISTS (
                  SELECT 1 FROM iacs_vessels_current ic WHERE ic.imo = vp.imo
              )
              AND vp.iacs_data IS NULL
            """
        )
        no_class_count = cur.rowcount
        if no_class_count > 0:
            logger.info("Marked %d tracked vessels as NO_IACS_CLASS", no_class_count)

    conn.commit()

    counts = {
        "added": added,
        "changed": changed,
        "removed": removed,
        "total_changes": len(changes),
        "high_risk_changes": sum(1 for c in changes if c["is_high_risk"]),
    }

    logger.info(
        "Snapshot %s: %d vessels | +%d added, ~%d changed, -%d removed | %d total changes (%d high-risk)",
        filename, len(summaries), added, changed, removed,
        len(changes), counts["high_risk_changes"],
    )

    # Print high-risk changes
    hr = [c for c in changes if c["is_high_risk"]]
    if hr:
        logger.info("=== HIGH-RISK CHANGES ===")
        for c in hr[:50]:  # Cap output
            logger.info(
                "  IMO %s (%s): %s %s → %s",
                c["imo"], c["ship_name"] or "?",
                c["change_type"],
                c.get("old_value", ""),
                c.get("new_value", ""),
            )
        if len(hr) > 50:
            logger.info("  ... and %d more", len(hr) - 50)

    return counts


# ---------------------------------------------------------------------------
# Integration API — query functions for Heimdal enrichment
# ---------------------------------------------------------------------------

def check_vessel(conn, imo: int) -> dict[str, Any]:
    """Check IACS class status for a single vessel.

    Returns dict with:
        - status: current IACS status or 'NO_IACS_CLASS'
        - risk_signal: risk level (none, low, moderate, high, critical)
        - class_society: current class society
        - reason: status reason
        - last_seen: when last seen in IACS file
        - changes: recent change history
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Current state
        cur.execute("SELECT * FROM iacs_vessels_current WHERE imo = %s", (imo,))
        current = cur.fetchone()

        # Recent changes (last 90 days)
        cur.execute(
            """
            SELECT change_type, field_changed, old_value, new_value,
                   is_high_risk, detected_at, snapshot_date
            FROM iacs_vessels_changes
            WHERE imo = %s
            ORDER BY detected_at DESC
            LIMIT 20
            """,
            (imo,),
        )
        changes = [dict(r) for r in cur.fetchall()]

    if not current:
        return {
            "imo": imo,
            "status": "NO_IACS_CLASS",
            "risk_signal": "moderate",
            "class_society": None,
            "reason": "Vessel not found in any IACS classification society records",
            "last_seen": None,
            "changes": [],
        }

    current = dict(current)
    status = current.get("status", "")

    # Determine risk signal
    if status == "Withdrawn":
        reason = current.get("reason", "")
        if "by society" in reason.lower():
            risk_signal = "critical"
        elif "non-compliance" in reason.lower():
            risk_signal = "high"
        else:
            risk_signal = "high"
    elif status == "Suspended":
        risk_signal = "high"
    elif status == "Removed":
        risk_signal = "high"
    elif status in ("Delivered", "Reinstated"):
        risk_signal = "none"
    else:
        risk_signal = "low"

    return {
        "imo": imo,
        "status": status,
        "risk_signal": risk_signal,
        "class_society": current.get("class_society"),
        "reason": current.get("reason"),
        "last_seen": current.get("last_seen"),
        "all_entries": current.get("all_entries"),
        "changes": changes,
    }


def get_risk_vessels(conn) -> list[dict[str, Any]]:
    """Return all vessels currently in Withdrawn or Suspended state."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT imo, ship_name, class_society, status, reason,
                   date_of_latest_status, last_seen, snapshot_date
            FROM iacs_vessels_current
            WHERE status IN ('Withdrawn', 'Suspended', 'Removed')
            ORDER BY date_of_latest_status DESC NULLS LAST
            """
        )
        return [dict(r) for r in cur.fetchall()]


def get_recent_changes(conn, days: int = 7) -> list[dict[str, Any]]:
    """Return all changes detected in the last N days."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT imo, ship_name, change_type, field_changed,
                   old_value, new_value, is_high_risk, detected_at, snapshot_date
            FROM iacs_vessels_changes
            WHERE detected_at >= NOW() - INTERVAL '%s days'
            ORDER BY is_high_risk DESC, detected_at DESC
            """,
            (days,),
        )
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def extract_date_from_filename(filename: str) -> date:
    """Extract snapshot date from filename like EquasisToIACS_20260320_949.zip."""
    match = re.search(r"EquasisToIACS_(\d{8})", filename)
    if not match:
        raise ValueError(f"Cannot extract date from filename: {filename}")
    d = match.group(1)
    return date(int(d[:4]), int(d[4:6]), int(d[6:8]))


def process_file(conn, zip_path: Path, original_filename: str | None = None) -> dict[str, int] | None:
    """Process a single IACS zip file: parse, diff, store.

    Returns change counts or None if already processed.
    """
    filename = original_filename or zip_path.name
    snapshot_date = extract_date_from_filename(filename)

    logger.info("Processing %s (date: %s)", filename, snapshot_date)

    entries, file_hash = parse_csv(zip_path)
    if not entries:
        logger.warning("No valid entries in %s", filename)
        return None

    if is_already_processed(conn, file_hash):
        logger.info("Already processed (hash %s), skipping", file_hash)
        return None

    summaries = aggregate_by_imo(entries)
    logger.info("Aggregated %d entries → %d unique vessels", len(entries), len(summaries))

    return diff_and_store(conn, summaries, snapshot_date, filename, file_hash)


def _download_process_cleanup(conn, url: str, filename: str) -> dict[str, int] | None:
    """Download, process, and delete a single IACS zip file."""
    zip_path = download_file(url)
    try:
        return process_file(conn, zip_path, original_filename=filename)
    finally:
        zip_path.unlink(missing_ok=True)
        logger.debug("Cleaned up temp file")


def run_bootstrap(conn) -> None:
    """Download and import all available IACS files, oldest-first."""
    links = scrape_download_links()
    if not links:
        logger.error("No download links found on IACS page")
        return

    logger.info("Bootstrap: importing %d files oldest-first", len(links))

    for link in links:
        try:
            _download_process_cleanup(conn, link["url"], link["filename"])
        except Exception:
            logger.exception("Failed to process %s", link["url"])


def run_latest(conn) -> None:
    """Download and import the latest IACS file."""
    links = scrape_download_links()
    if not links:
        logger.error("No download links found on IACS page")
        return

    latest = links[-1]  # Already sorted oldest-first
    logger.info("Latest file: %s", latest["filename"])

    _download_process_cleanup(conn, latest["url"], latest["filename"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="IACS Vessels-in-Class Tracker")
    parser.add_argument("--url", help="Download and import from a specific URL")
    parser.add_argument("--file", help="Import from a local zip file")
    parser.add_argument("--bootstrap", action="store_true",
                        help="Import all available files oldest-first")
    parser.add_argument("--check-vessel", type=int, metavar="IMO",
                        help="Query IACS status for a single vessel")
    parser.add_argument("--risk-vessels", action="store_true",
                        help="List all vessels with Withdrawn/Suspended status")
    parser.add_argument("--recent-changes", type=int, metavar="DAYS", nargs="?",
                        const=7, help="Show changes in last N days (default 7)")

    args = parser.parse_args()
    conn = get_connection()

    try:
        if args.check_vessel:
            import json
            result = check_vessel(conn, args.check_vessel)
            print(json.dumps(result, indent=2, default=str))

        elif args.risk_vessels:
            import json
            vessels = get_risk_vessels(conn)
            print(json.dumps(vessels, indent=2, default=str))
            logger.info("Total risk vessels: %d", len(vessels))

        elif args.recent_changes is not None:
            import json
            changes = get_recent_changes(conn, args.recent_changes)
            print(json.dumps(changes, indent=2, default=str))
            logger.info("Total changes in last %d days: %d", args.recent_changes, len(changes))

        elif args.url:
            match = re.search(r"(EquasisToIACS_\d{8}_\d+\.zip)", args.url)
            fname = match.group(1) if match else args.url.split("/")[-1]
            _download_process_cleanup(conn, args.url, fname)

        elif args.file:
            process_file(conn, Path(args.file))

        elif args.bootstrap:
            run_bootstrap(conn)

        else:
            # Default: download and process latest
            run_latest(conn)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
