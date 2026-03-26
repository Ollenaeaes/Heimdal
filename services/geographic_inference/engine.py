"""Geographic Inference Engine — AIS-derived signals D1-D7.

Detects Baltic/Barents Russian-origin transits, staging area loitering,
loiter-then-vanish patterns, MMSI/flag mismatches, and STS with blacklisted
vessels from AIS position data.

Results are stored in the PostgreSQL ``vessel_signals`` table.

Usage:
    python -m services.geographic_inference.engine [--mmsi 123456789]
    # Or call GeographicInference(conn).evaluate_vessel(mmsi)

Environment:
    DATABASE_URL — PostgreSQL connection string
"""

from __future__ import annotations

import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import psycopg2
import psycopg2.extras

from shared.config import settings
from shared.constants import MID_TO_FLAG

logger = logging.getLogger("geographic-inference")

# ---------------------------------------------------------------------------
# Geographic zone definitions (WKT polygons)
# ---------------------------------------------------------------------------

# Gulf of Finland approaches — staging area for Primorsk/Ust-Luga/Vysotsk exports
# Covers the area from Tallinn to Helsinki, extending east toward Gogland Island
GULF_OF_FINLAND_APPROACHES_WKT = (
    "POLYGON(("
    "24.5 59.3, 27.5 59.3, 28.5 59.8, 28.5 60.2, "
    "27.5 60.3, 24.5 60.0, 24.5 59.3"
    "))"
)

# Kola Bay approaches — staging area for Murmansk oil terminal
# Covers the Barents Sea approach to Murmansk
KOLA_BAY_APPROACHES_WKT = (
    "POLYGON(("
    "32.0 68.5, 34.5 68.5, 34.5 69.5, 33.5 69.5, "
    "32.0 69.2, 32.0 68.5"
    "))"
)

# Baltic transit corridor — from Skagen/Kattegat through the Baltic
# Vessels transiting south from Russian ports would pass through here
BALTIC_TRANSIT_WKT = (
    "POLYGON(("
    "10.0 54.5, 24.0 54.5, 28.0 59.0, 28.0 60.5, "
    "24.0 60.5, 10.0 58.0, 10.0 54.5"
    "))"
)

# Barents transit corridor — south past Finnmark/North Cape
BARENTS_TRANSIT_WKT = (
    "POLYGON(("
    "20.0 69.0, 35.0 69.0, 35.0 72.0, 20.0 72.0, 20.0 69.0"
    "))"
)

# Non-Russian Baltic terminal zones (for D3 — checking port call footprints)
# If a vessel has called at any of these, D3 should NOT fire.
NON_RUSSIAN_BALTIC_TERMINALS = {
    "Gdańsk": "POLYGON((18.5 54.3, 18.8 54.3, 18.8 54.5, 18.5 54.5, 18.5 54.3))",
    "Butinge": "POLYGON((20.9 55.9, 21.2 55.9, 21.2 56.1, 20.9 56.1, 20.9 55.9))",
    "Nynäshamn": "POLYGON((17.8 58.8, 18.1 58.8, 18.1 59.0, 17.8 59.0, 17.8 58.8))",
    # Finnish refineries
    "Porvoo/Sköldvik": "POLYGON((25.4 60.2, 25.7 60.2, 25.7 60.4, 25.4 60.4, 25.4 60.2))",
    "Naantali": "POLYGON((21.9 60.4, 22.2 60.4, 22.2 60.6, 21.9 60.6, 21.9 60.4))",
}

# Melkøya LNG terminal — for D4 (Barents non-Russian origin check)
MELKOYA_TERMINAL_WKT = (
    "POLYGON(("
    "23.4 70.6, 23.8 70.6, 23.8 70.8, 23.4 70.8, 23.4 70.6"
    "))"
)

# Russian terminals (for D7 — "goes dark toward Russian port")
RUSSIAN_TERMINAL_POINTS = {
    "Primorsk": (60.35, 28.67),
    "Ust-Luga": (59.68, 28.40),
    "Vysotsk": (60.63, 28.57),
    "Murmansk": (68.97, 33.08),
    "Novorossiysk": (44.72, 37.79),
}

# Tanker ship types (AIS ship type codes for tankers)
TANKER_SHIP_TYPES = frozenset({80, 81, 82, 83, 84, 85, 86, 87, 88, 89})

# Signal weights
SIGNAL_WEIGHTS = {
    "D1": 3,  # Staging area loiter — Gulf of Finland
    "D2": 3,  # Staging area loiter — Kola Bay
    "D3": 4,  # Baltic Russian-origin transit
    "D4": 4,  # Barents Russian-origin transit
    "D5": 2,  # MMSI/flag mismatch
    "D6": 4,  # STS with blacklisted/red vessel
    "D7": 4,  # Loiter-then-vanish
}

# Thresholds
STAGING_LOITER_HOURS = 12
AIS_GAP_HOURS = 6


# ---------------------------------------------------------------------------
# Helper: sync PostgreSQL connection
# ---------------------------------------------------------------------------

def _get_sync_dsn() -> str:
    """Convert async DATABASE_URL to sync psycopg2 DSN."""
    url = os.environ.get("DATABASE_URL", settings.database_url.get_secret_value())
    url = re.sub(r"postgresql\+asyncpg://", "postgresql://", url)
    return url


def _get_pg_connection():
    """Return a psycopg2 connection."""
    return psycopg2.connect(_get_sync_dsn())


def _bearing_to_point(from_lat: float, from_lon: float,
                      to_lat: float, to_lon: float) -> float:
    """Calculate bearing from one point to another (degrees, 0=N clockwise)."""
    lat1 = math.radians(from_lat)
    lat2 = math.radians(to_lat)
    dlon = math.radians(to_lon - from_lon)
    x = math.sin(dlon) * math.cos(lat2)
    y = (math.cos(lat1) * math.sin(lat2) -
         math.sin(lat1) * math.cos(lat2) * math.cos(dlon))
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


def _bearing_difference(b1: float, b2: float) -> float:
    """Absolute angular difference between two bearings (0-180)."""
    diff = abs(b1 - b2) % 360
    return min(diff, 360 - diff)


# ---------------------------------------------------------------------------
# Geographic Inference Engine
# ---------------------------------------------------------------------------

class GeographicInference:
    """Evaluates AIS data for a vessel and produces D1-D7 signals.

    Parameters
    ----------
    conn : psycopg2 connection
        Sync PostgreSQL connection for reading vessel_positions, vessel_profiles,
        and anomaly_events.
    lookback_days : int
        How many days of position history to analyze (default 30).
    """

    def __init__(self, conn, lookback_days: int = 30):
        self.conn = conn
        self.lookback_days = lookback_days

    def evaluate_vessel(self, mmsi: int) -> list[dict[str, Any]]:
        """Evaluate a single vessel and return triggered signals.

        Returns a list of dicts:
            {signal_id, weight, details, source_data}
        """
        signals: list[dict[str, Any]] = []

        # Fetch vessel profile
        profile = self._get_vessel_profile(mmsi)
        if not profile:
            logger.debug("No profile for MMSI %d, skipping", mmsi)
            return signals

        # Fetch recent positions
        positions = self._get_recent_positions(mmsi)

        # D1: Gulf of Finland staging area loiter
        d1 = self._check_staging_loiter(
            mmsi, positions,
            GULF_OF_FINLAND_APPROACHES_WKT,
            "D1", "Gulf of Finland approaches",
        )
        if d1:
            signals.append(d1)

        # D2: Kola Bay staging area loiter
        d2 = self._check_staging_loiter(
            mmsi, positions,
            KOLA_BAY_APPROACHES_WKT,
            "D2", "Kola Bay approaches",
        )
        if d2:
            signals.append(d2)

        # D3: Baltic Russian-origin transit (tankers only)
        ship_type = profile.get("ship_type")
        if ship_type and ship_type in TANKER_SHIP_TYPES:
            d3 = self._check_baltic_transit(mmsi, positions)
            if d3:
                signals.append(d3)

            # D4: Barents Russian-origin transit (tankers only)
            d4 = self._check_barents_transit(mmsi, positions)
            if d4:
                signals.append(d4)

        # D5: MMSI/flag mismatch
        d5 = self._check_mmsi_flag_mismatch(mmsi, profile)
        if d5:
            signals.append(d5)

        # D6: STS with blacklisted/red vessel
        d6 = self._check_sts_with_blacklisted(mmsi)
        if d6:
            signals.append(d6)

        # D7: Loiter-then-vanish
        d7 = self._check_loiter_then_vanish(mmsi, positions)
        if d7:
            signals.append(d7)

        return signals

    # ------------------------------------------------------------------
    # Data access helpers
    # ------------------------------------------------------------------

    def _get_vessel_profile(self, mmsi: int) -> Optional[dict]:
        """Fetch vessel profile from vessel_profiles."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT mmsi, imo, ship_type, flag_country, risk_tier "
                "FROM vessel_profiles WHERE mmsi = %s",
                (mmsi,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def _get_recent_positions(self, mmsi: int) -> list[dict]:
        """Fetch recent positions with lat/lon extracted from geography."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT mmsi, timestamp,
                       ST_Y(position::geometry) AS lat,
                       ST_X(position::geometry) AS lon,
                       sog, cog, nav_status
                FROM vessel_positions
                WHERE mmsi = %s AND timestamp >= %s
                ORDER BY timestamp ASC
                """,
                (mmsi, cutoff),
            )
            return [dict(r) for r in cur.fetchall()]

    def _has_port_call_footprint(self, mmsi: int, terminal_wkt: str) -> bool:
        """Check if vessel has moored/slow positions within a terminal zone.

        Port call footprint = positions with nav_status=5 (moored) or SOG<0.5
        within the terminal polygon.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS(
                    SELECT 1 FROM vessel_positions
                    WHERE mmsi = %s
                      AND timestamp >= %s
                      AND (nav_status = 5 OR sog < 0.5)
                      AND ST_Within(
                          position::geometry,
                          ST_GeomFromText(%s, 4326)
                      )
                    LIMIT 1
                )
                """,
                (mmsi, cutoff, terminal_wkt),
            )
            return cur.fetchone()[0]

    def _positions_in_zone(self, positions: list[dict],
                           zone_wkt: str) -> list[dict]:
        """Filter positions that fall within a WKT polygon (in-memory check).

        Uses PostGIS for the actual spatial query.
        """
        if not positions:
            return []

        mmsi = positions[0]["mmsi"]
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT mmsi, timestamp,
                       ST_Y(position::geometry) AS lat,
                       ST_X(position::geometry) AS lon,
                       sog, cog, nav_status
                FROM vessel_positions
                WHERE mmsi = %s
                  AND timestamp >= %s
                  AND ST_Within(
                      position::geometry,
                      ST_GeomFromText(%s, 4326)
                  )
                ORDER BY timestamp ASC
                """,
                (mmsi, cutoff, zone_wkt),
            )
            return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # D1/D2: Staging area loiter
    # ------------------------------------------------------------------

    def _check_staging_loiter(
        self, mmsi: int, positions: list[dict],
        zone_wkt: str, signal_id: str, zone_name: str,
    ) -> Optional[dict[str, Any]]:
        """Detect loitering in a staging area for >12 hours.

        A vessel is considered loitering if it has positions within the zone
        with nav_status=1 (at anchor) or SOG<1.0 spanning more than 12 hours.
        """
        zone_positions = self._positions_in_zone(positions, zone_wkt)
        if not zone_positions:
            return None

        # Filter to anchored/slow positions
        loiter_positions = [
            p for p in zone_positions
            if (p.get("nav_status") == 1 or
                (p.get("sog") is not None and p["sog"] < 1.0))
        ]
        if not loiter_positions:
            return None

        # Calculate total loiter duration
        first_ts = loiter_positions[0]["timestamp"]
        last_ts = loiter_positions[-1]["timestamp"]
        duration_hours = (last_ts - first_ts).total_seconds() / 3600

        if duration_hours < STAGING_LOITER_HOURS:
            return None

        return {
            "signal_id": signal_id,
            "weight": SIGNAL_WEIGHTS[signal_id],
            "details": {
                "zone": zone_name,
                "duration_hours": round(duration_hours, 1),
                "position_count": len(loiter_positions),
                "first_seen": first_ts.isoformat(),
                "last_seen": last_ts.isoformat(),
            },
            "source_data": f"vessel_positions: {len(loiter_positions)} anchored positions in {zone_name}",
        }

    # ------------------------------------------------------------------
    # D3: Baltic Russian-origin transit
    # ------------------------------------------------------------------

    def _check_baltic_transit(self, mmsi: int,
                              positions: list[dict]) -> Optional[dict[str, Any]]:
        """Detect tanker transiting south in Baltic with no non-Russian terminal footprint."""
        # Check if vessel has positions in Baltic transit corridor
        baltic_positions = self._positions_in_zone(positions, BALTIC_TRANSIT_WKT)
        if not baltic_positions:
            return None

        # Must have southbound positions (COG roughly 150-250 degrees)
        southbound = [
            p for p in baltic_positions
            if p.get("cog") is not None and 150 <= p["cog"] <= 250
        ]
        if not southbound:
            return None

        # Check for port call footprint at any non-Russian Baltic terminal
        for terminal_name, terminal_wkt in NON_RUSSIAN_BALTIC_TERMINALS.items():
            if self._has_port_call_footprint(mmsi, terminal_wkt):
                logger.debug(
                    "MMSI %d has port call at %s, D3 suppressed",
                    mmsi, terminal_name,
                )
                return None

        return {
            "signal_id": "D3",
            "weight": SIGNAL_WEIGHTS["D3"],
            "details": {
                "description": "Baltic Russian-origin transit — no non-Russian terminal footprint",
                "southbound_positions": len(southbound),
                "terminals_checked": list(NON_RUSSIAN_BALTIC_TERMINALS.keys()),
            },
            "source_data": f"vessel_positions: {len(baltic_positions)} positions in Baltic corridor",
        }

    # ------------------------------------------------------------------
    # D4: Barents Russian-origin transit
    # ------------------------------------------------------------------

    def _check_barents_transit(self, mmsi: int,
                               positions: list[dict]) -> Optional[dict[str, Any]]:
        """Detect tanker heading south past Finnmark with no Melkøya origin."""
        barents_positions = self._positions_in_zone(positions, BARENTS_TRANSIT_WKT)
        if not barents_positions:
            return None

        # Must have southbound positions (COG roughly 150-250 degrees)
        southbound = [
            p for p in barents_positions
            if p.get("cog") is not None and 150 <= p["cog"] <= 250
        ]
        if not southbound:
            return None

        # Check for Melkøya origin
        if self._has_port_call_footprint(mmsi, MELKOYA_TERMINAL_WKT):
            logger.debug("MMSI %d has Melkøya footprint, D4 suppressed", mmsi)
            return None

        return {
            "signal_id": "D4",
            "weight": SIGNAL_WEIGHTS["D4"],
            "details": {
                "description": "Barents Russian-origin transit — no Melkøya origin",
                "southbound_positions": len(southbound),
            },
            "source_data": f"vessel_positions: {len(barents_positions)} positions past Finnmark",
        }

    # ------------------------------------------------------------------
    # D5: MMSI/flag mismatch
    # ------------------------------------------------------------------

    def _check_mmsi_flag_mismatch(self, mmsi: int,
                                   profile: dict) -> Optional[dict[str, Any]]:
        """Detect when MMSI MID maps to a different flag than recorded."""
        mmsi_str = str(mmsi)
        if len(mmsi_str) < 3:
            return None

        mid = int(mmsi_str[:3])
        mid_flag = MID_TO_FLAG.get(mid)
        if not mid_flag:
            return None

        recorded_flag = profile.get("flag_country")
        if not recorded_flag:
            return None

        # Normalize both to uppercase alpha-2
        recorded_flag = recorded_flag.strip().upper()
        if len(recorded_flag) > 2:
            # Try to handle alpha-3 or full country names
            from shared.constants import normalize_flag
            recorded_flag = normalize_flag(recorded_flag) or recorded_flag

        if mid_flag == recorded_flag:
            return None

        return {
            "signal_id": "D5",
            "weight": SIGNAL_WEIGHTS["D5"],
            "details": {
                "mmsi_mid": mid,
                "mid_flag": mid_flag,
                "recorded_flag": recorded_flag,
                "description": f"MMSI MID {mid} maps to {mid_flag} but recorded flag is {recorded_flag}",
            },
            "source_data": f"vessel_profiles: flag_country={recorded_flag}, MID={mid}→{mid_flag}",
        }

    # ------------------------------------------------------------------
    # D6: STS with blacklisted/red vessel
    # ------------------------------------------------------------------

    def _check_sts_with_blacklisted(self, mmsi: int) -> Optional[dict[str, Any]]:
        """Detect STS proximity events where the partner vessel is red/blacklisted."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Find STS proximity events for this vessel
            cur.execute(
                """
                SELECT ae.details, ae.created_at
                FROM anomaly_events ae
                WHERE ae.mmsi = %s
                  AND ae.rule_id = 'sts_proximity'
                ORDER BY ae.created_at DESC
                LIMIT 50
                """,
                (mmsi,),
            )
            sts_events = cur.fetchall()

        if not sts_events:
            return None

        for event in sts_events:
            details = event.get("details", {})
            partner_mmsi = details.get("partner_mmsi")
            if not partner_mmsi:
                continue

            # Check if partner is red or blacklisted
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT risk_tier, sanctions_status FROM vessel_profiles WHERE mmsi = %s",
                    (int(partner_mmsi),),
                )
                partner = cur.fetchone()

            if not partner:
                continue

            partner_tier = partner.get("risk_tier")
            sanctions = partner.get("sanctions_status", {})
            is_blacklisted = (
                isinstance(sanctions, dict) and
                sanctions.get("status") == "sanctioned"
            )

            if partner_tier == "red" or is_blacklisted:
                return {
                    "signal_id": "D6",
                    "weight": SIGNAL_WEIGHTS["D6"],
                    "details": {
                        "partner_mmsi": partner_mmsi,
                        "partner_tier": partner_tier,
                        "partner_blacklisted": is_blacklisted,
                        "sts_date": event["created_at"].isoformat() if event.get("created_at") else None,
                        "description": f"STS with {'blacklisted' if is_blacklisted else 'red'} vessel MMSI {partner_mmsi}",
                    },
                    "source_data": f"anomaly_events: sts_proximity with partner {partner_mmsi}",
                }

        return None

    # ------------------------------------------------------------------
    # D7: Loiter-then-vanish
    # ------------------------------------------------------------------

    def _check_loiter_then_vanish(self, mmsi: int,
                                   positions: list[dict]) -> Optional[dict[str, Any]]:
        """Detect staging area loiter followed by AIS gap toward Russian port.

        Requirements:
        1. Vessel must have loitered in a staging area (Gulf of Finland or Kola Bay)
        2. After loitering, vessel must have an AIS gap of >6 hours
        3. Last known COG must point toward a Russian terminal
        """
        if not positions:
            return None

        # Check both staging areas
        staging_zones = [
            ("Gulf of Finland", GULF_OF_FINLAND_APPROACHES_WKT),
            ("Kola Bay", KOLA_BAY_APPROACHES_WKT),
        ]

        for zone_name, zone_wkt in staging_zones:
            zone_positions = self._positions_in_zone(positions, zone_wkt)
            if not zone_positions:
                continue

            # Check for loitering (anchored/slow for >12h)
            loiter_positions = [
                p for p in zone_positions
                if (p.get("nav_status") == 1 or
                    (p.get("sog") is not None and p["sog"] < 1.0))
            ]
            if not loiter_positions:
                continue

            first_ts = loiter_positions[0]["timestamp"]
            last_loiter_ts = loiter_positions[-1]["timestamp"]
            loiter_hours = (last_loiter_ts - first_ts).total_seconds() / 3600
            if loiter_hours < STAGING_LOITER_HOURS:
                continue

            # Now check for AIS gap after loitering
            # Find positions AFTER the loiter period
            post_loiter = [
                p for p in positions
                if p["timestamp"] > last_loiter_ts
            ]

            if not post_loiter:
                # No positions after loitering — check if the gap from
                # last loiter to now exceeds threshold
                now = datetime.now(timezone.utc)
                gap_hours = (now - last_loiter_ts).total_seconds() / 3600
                if gap_hours < AIS_GAP_HOURS:
                    continue

                # Check if last COG points toward a Russian terminal
                last_pos = loiter_positions[-1]
                if self._cog_toward_russian_terminal(last_pos):
                    return {
                        "signal_id": "D7",
                        "weight": SIGNAL_WEIGHTS["D7"],
                        "details": {
                            "staging_zone": zone_name,
                            "loiter_hours": round(loiter_hours, 1),
                            "gap_hours": round(gap_hours, 1),
                            "last_lat": last_pos["lat"],
                            "last_lon": last_pos["lon"],
                            "last_cog": last_pos.get("cog"),
                            "description": f"Loitered in {zone_name} for {loiter_hours:.0f}h then went dark toward Russian port",
                        },
                        "source_data": f"vessel_positions: loiter + AIS gap from {zone_name}",
                    }
            else:
                # Check for gaps within post-loiter positions
                for i in range(len(post_loiter) - 1):
                    gap = (post_loiter[i + 1]["timestamp"] - post_loiter[i]["timestamp"]).total_seconds() / 3600
                    if gap >= AIS_GAP_HOURS:
                        pos_before_gap = post_loiter[i]
                        if self._cog_toward_russian_terminal(pos_before_gap):
                            return {
                                "signal_id": "D7",
                                "weight": SIGNAL_WEIGHTS["D7"],
                                "details": {
                                    "staging_zone": zone_name,
                                    "loiter_hours": round(loiter_hours, 1),
                                    "gap_hours": round(gap, 1),
                                    "last_lat": pos_before_gap["lat"],
                                    "last_lon": pos_before_gap["lon"],
                                    "last_cog": pos_before_gap.get("cog"),
                                    "description": f"Loitered in {zone_name} then went dark toward Russian port",
                                },
                                "source_data": f"vessel_positions: loiter + AIS gap from {zone_name}",
                            }

        return None

    def _cog_toward_russian_terminal(self, position: dict) -> bool:
        """Check if the vessel's COG points toward any Russian terminal.

        Returns True if COG is within 30 degrees of the bearing to any
        Russian terminal.
        """
        cog = position.get("cog")
        if cog is None:
            return False

        lat = position["lat"]
        lon = position["lon"]

        for terminal_name, (t_lat, t_lon) in RUSSIAN_TERMINAL_POINTS.items():
            bearing = _bearing_to_point(lat, lon, t_lat, t_lon)
            if _bearing_difference(cog, bearing) <= 30:
                return True

        return False

    # ------------------------------------------------------------------
    # Signal storage
    # ------------------------------------------------------------------

    def store_signals(self, mmsi: int, imo: Optional[int],
                      signals: list[dict[str, Any]]) -> int:
        """Write triggered signals to the vessel_signals table.

        Uses ON CONFLICT on the dedup index (mmsi, signal_id, date) to
        avoid duplicates when re-running.

        Returns the number of signals stored.
        """
        if not signals:
            return 0

        stored = 0
        with self.conn.cursor() as cur:
            for sig in signals:
                try:
                    cur.execute(
                        """
                        INSERT INTO vessel_signals
                            (mmsi, imo, signal_id, weight, triggered_at, details, source_data)
                        VALUES (%s, %s, %s, %s, NOW(), %s, %s)
                        ON CONFLICT (mmsi, signal_id, (triggered_at::date))
                        DO UPDATE SET
                            weight = EXCLUDED.weight,
                            details = EXCLUDED.details,
                            source_data = EXCLUDED.source_data,
                            triggered_at = EXCLUDED.triggered_at
                        """,
                        (
                            mmsi,
                            imo,
                            sig["signal_id"],
                            sig["weight"],
                            psycopg2.extras.Json(sig["details"]),
                            sig["source_data"],
                        ),
                    )
                    stored += 1
                except Exception:
                    logger.exception(
                        "Failed to store signal %s for MMSI %d",
                        sig["signal_id"], mmsi,
                    )
            self.conn.commit()

        return stored


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """Run geographic inference for all tankers or a specific MMSI."""
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Geographic Inference Engine")
    parser.add_argument("--mmsi", type=int, help="Evaluate a specific MMSI")
    args = parser.parse_args()

    conn = _get_pg_connection()
    engine = GeographicInference(conn)

    try:
        if args.mmsi:
            mmsis = [args.mmsi]
        else:
            # Evaluate all tankers
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT mmsi, imo FROM vessel_profiles "
                    "WHERE ship_type BETWEEN 80 AND 89"
                )
                rows = cur.fetchall()
                mmsis = [r[0] for r in rows]
            logger.info("Evaluating %d tankers", len(mmsis))

        total_signals = 0
        for mmsi in mmsis:
            signals = engine.evaluate_vessel(mmsi)
            if signals:
                profile = engine._get_vessel_profile(mmsi)
                imo = profile.get("imo") if profile else None
                stored = engine.store_signals(mmsi, imo, signals)
                total_signals += stored
                for sig in signals:
                    logger.info(
                        "MMSI %d: %s (weight=%d) — %s",
                        mmsi, sig["signal_id"], sig["weight"],
                        sig["details"].get("description", ""),
                    )

        logger.info("Done. %d signals stored for %d vessels.", total_signals, len(mmsis))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
