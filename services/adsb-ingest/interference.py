"""Interference detection module.

Consumes NACp data from all aircraft observations, bins into H3 cells,
detects interference events, and manages event lifecycle.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import h3
import asyncpg

logger = logging.getLogger("adsb-ingest.interference")

# H3 resolution 5 ≈ 8.5 km edge length, ~253 km² area
H3_RESOLUTION = 5

# Detection thresholds
NACP_DEGRADED_THRESHOLD = 5     # NACp <= 5 is considered degraded
NACP_NORMAL_THRESHOLD = 8       # NACp >= 8 is considered normal
MIN_DEGRADED_COUNT = 2          # minimum degraded aircraft to declare event
MIN_DEGRADED_RATIO = 0.3        # 30% of observed aircraft must be degraded
OBSERVATION_WINDOW_SECONDS = 300  # 5-minute rolling window

# Event lifecycle
EVENT_EXTEND_SECONDS = 600      # extend active event by 10 min on new observations
EVENT_CLOSE_SECONDS = 900       # close event after 15 min without observations

# Severity thresholds
SEVERE_NACP_THRESHOLD = 3       # NACp <= 3 or gpsOkBefore = severe


@dataclass
class CellObservation:
    """Rolling observation window for an H3 cell."""
    aircraft: dict[str, float] = field(default_factory=dict)  # hex -> last_nac_p
    degraded: dict[str, float] = field(default_factory=dict)  # hex -> nac_p (degraded only)
    gps_lost: set[str] = field(default_factory=set)  # hex codes with gpsOkBefore
    altitudes: list[int] = field(default_factory=list)
    last_update: float = 0.0


class InterferenceDetector:
    """Detects GNSS interference from ADS-B NACp observations."""

    def __init__(self):
        # h3_index -> CellObservation
        self._cells: dict[int, CellObservation] = defaultdict(CellObservation)
        # Active events: h3_index -> event_id (from DB)
        self._active_events: dict[int, int] = {}
        self._last_cleanup = time.monotonic()

    def process_aircraft(self, aircraft: list[dict], now: float | None = None) -> list[dict]:
        """Process a batch of aircraft observations and return interference signals.

        Each aircraft dict is a raw adsb.lol response object.
        Returns list of interference signal dicts for cells that meet thresholds.
        """
        now = now or time.monotonic()
        ts = datetime.now(timezone.utc)

        # Bin observations by H3 cell
        for ac in aircraft:
            lat = ac.get("lat")
            lon = ac.get("lon")
            nac_p = ac.get("nac_p")
            hex_code = ac.get("hex", "").lower()

            if lat is None or lon is None or not hex_code:
                continue

            # Skip ADS-B version 0 (doesn't reliably report NACp)
            version = ac.get("version")
            if version is not None and version < 1:
                continue

            # Skip aircraft on the ground
            alt = ac.get("alt_baro")
            if alt == "ground" or alt is None:
                continue
            if isinstance(alt, str):
                try:
                    alt = int(alt)
                except ValueError:
                    continue

            try:
                h3_index = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
            except Exception:
                continue

            cell = self._cells[h3_index]
            cell.last_update = now

            # Record observation
            cell.aircraft[hex_code] = nac_p if nac_p is not None else -1
            cell.altitudes.append(alt)

            # Check degradation
            if nac_p is not None and 1 <= nac_p <= NACP_DEGRADED_THRESHOLD:
                cell.degraded[hex_code] = nac_p
            elif nac_p is not None and nac_p > NACP_DEGRADED_THRESHOLD:
                # Aircraft recovered — remove from degraded
                cell.degraded.pop(hex_code, None)

            # Check gpsOkBefore flag
            if ac.get("gpsOkBefore") is not None:
                cell.gps_lost.add(hex_code)

        # Evaluate cells for interference
        signals = []
        for h3_index, cell in self._cells.items():
            signal = self._evaluate_cell(h3_index, cell, ts)
            if signal:
                signals.append(signal)

        # Periodic cleanup of stale cells
        if now - self._last_cleanup > 120:
            self._cleanup_stale_cells(now)
            self._last_cleanup = now

        return signals

    def _evaluate_cell(
        self, h3_index: int, cell: CellObservation, ts: datetime
    ) -> dict | None:
        """Evaluate a cell for interference conditions. Returns signal dict or None."""
        aircraft_count = len(cell.aircraft)
        degraded_count = len(cell.degraded)
        gps_lost_count = len(cell.gps_lost)

        if aircraft_count == 0:
            return None

        # Detection conditions (from spec):
        # 1. Multi-aircraft NACp degradation
        multi_aircraft = (
            degraded_count >= MIN_DEGRADED_COUNT
            and degraded_count / aircraft_count >= MIN_DEGRADED_RATIO
        )
        # 2. Direct GPS loss flag (high confidence for single aircraft)
        gps_lost = gps_lost_count > 0

        if not multi_aircraft and not gps_lost:
            return None

        # Calculate severity
        min_nac_p = min(cell.degraded.values()) if cell.degraded else None
        if gps_lost or (min_nac_p is not None and min_nac_p <= SEVERE_NACP_THRESHOLD):
            severity = "severe"
        else:
            severity = "moderate"

        # Calculate confidence
        if multi_aircraft and gps_lost:
            confidence = 0.95
        elif multi_aircraft:
            ratio = degraded_count / aircraft_count
            confidence = min(0.5 + ratio * 0.4 + (degraded_count - 2) * 0.05, 0.9)
        else:
            # Single aircraft gpsOkBefore
            confidence = 0.7

        # Get cell center
        center_lat, center_lon = h3.cell_to_latlng(h3_index)

        # Convert H3 hex string to integer for DB storage
        h3_int = int(h3_index, 16)

        # H3 res 5 edge ≈ 8.5 km, so cell radius ≈ 8.5 km
        radius_km = 8.5

        avg_alt = int(sum(cell.altitudes) / len(cell.altitudes)) if cell.altitudes else None

        return {
            "h3_index": h3_int,
            "center_lat": center_lat,
            "center_lon": center_lon,
            "radius_km": radius_km,
            "aircraft_count": aircraft_count,
            "degraded_count": degraded_count,
            "gps_lost_count": gps_lost_count,
            "min_nac_p": min_nac_p,
            "severity": severity,
            "confidence": confidence,
            "avg_alt_baro": avg_alt,
            "timestamp": ts,
        }

    def _cleanup_stale_cells(self, now: float) -> None:
        """Remove cells that haven't been updated recently."""
        stale = [
            h3_idx for h3_idx, cell in self._cells.items()
            if now - cell.last_update > OBSERVATION_WINDOW_SECONDS
        ]
        for h3_idx in stale:
            del self._cells[h3_idx]
        if stale:
            logger.debug("Cleaned up %d stale H3 cells", len(stale))

    async def persist_observations(
        self, pool: asyncpg.Pool, signals: list[dict]
    ) -> None:
        """Write interference observations to the database."""
        if not signals:
            return

        rows = [
            (
                s["timestamp"], s["h3_index"], H3_RESOLUTION,
                s["center_lat"], s["center_lon"],
                s["aircraft_count"], s["degraded_count"],
                s["min_nac_p"], s["gps_lost_count"], s["avg_alt_baro"],
            )
            for s in signals
        ]

        async with pool.acquire() as conn:
            await conn.executemany(
                """INSERT INTO adsb_interference_observations
                   (time, h3_index, h3_resolution, center_lat, center_lon,
                    aircraft_count, degraded_count, min_nac_p, gps_lost_count, avg_alt_baro)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                rows,
            )

    async def persist_events(
        self, pool: asyncpg.Pool, signals: list[dict]
    ) -> None:
        """Create or update interference events based on detection signals."""
        if not signals:
            return

        now = datetime.now(timezone.utc)

        async with pool.acquire() as conn:
            for signal in signals:
                h3_idx = signal["h3_index"]

                # Check for existing active event in this cell
                existing = await conn.fetchrow(
                    """SELECT id, time_end, peak_aircraft_affected, min_nac_p_observed
                       FROM adsb_interference_events
                       WHERE h3_index = $1 AND is_active = TRUE
                       ORDER BY time_start DESC LIMIT 1""",
                    h3_idx,
                )

                if existing:
                    # Extend existing event
                    new_end = now + timedelta(seconds=EVENT_EXTEND_SECONDS)
                    peak = max(existing["peak_aircraft_affected"], signal["degraded_count"])
                    min_nac = signal["min_nac_p"]
                    if existing["min_nac_p_observed"] is not None:
                        if min_nac is None or existing["min_nac_p_observed"] < min_nac:
                            min_nac = existing["min_nac_p_observed"]

                    await conn.execute(
                        """UPDATE adsb_interference_events
                           SET time_end = $1,
                               peak_aircraft_affected = $2,
                               min_nac_p_observed = $3,
                               severity = $4,
                               confidence = GREATEST(confidence, $5)
                           WHERE id = $6 AND time_start = $7""",
                        new_end, peak, min_nac,
                        signal["severity"], signal["confidence"],
                        existing["id"], existing["time_end"] - timedelta(seconds=EVENT_EXTEND_SECONDS),
                    )
                    # The UPDATE above won't work well with hypertables since time_start
                    # is the partition key. Use a simpler approach:
                    await conn.execute(
                        """UPDATE adsb_interference_events
                           SET time_end = $1,
                               peak_aircraft_affected = $2,
                               min_nac_p_observed = $3,
                               severity = $4,
                               confidence = GREATEST(confidence, $5)
                           WHERE id = $6""",
                        new_end, peak, min_nac,
                        signal["severity"], signal["confidence"],
                        existing["id"],
                    )
                else:
                    # Create new event
                    event_end = now + timedelta(seconds=EVENT_EXTEND_SECONDS)
                    await conn.execute(
                        """INSERT INTO adsb_interference_events
                           (time_start, time_end, h3_index, center_lat, center_lon,
                            radius_km, severity, event_type, confidence,
                            peak_aircraft_affected, min_nac_p_observed, is_active)
                           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, TRUE)""",
                        now, event_end,
                        signal["h3_index"], signal["center_lat"], signal["center_lon"],
                        signal["radius_km"], signal["severity"], "jamming",
                        signal["confidence"], signal["degraded_count"],
                        signal["min_nac_p"],
                    )
                    logger.info(
                        "New interference event: h3=%s severity=%s confidence=%.2f "
                        "degraded=%d/%d at (%.2f, %.2f)",
                        hex(h3_idx), signal["severity"], signal["confidence"],
                        signal["degraded_count"], signal["aircraft_count"],
                        signal["center_lat"], signal["center_lon"],
                    )

            # Close stale events
            await conn.execute(
                """UPDATE adsb_interference_events
                   SET is_active = FALSE
                   WHERE is_active = TRUE AND time_end < $1""",
                now,
            )
