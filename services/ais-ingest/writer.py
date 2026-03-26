"""Batch writer for AIS positions and vessel profiles.

Buffers position reports and flushes in batches using asyncpg executemany
with PostGIS ST_MakePoint. Publishes flush events to Redis.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

try:
    import orjson

    def _json_dumps(obj):
        return orjson.dumps(obj).decode("utf-8")

except ImportError:
    import json

    _json_dumps = json.dumps
from typing import TYPE_CHECKING

import asyncpg

if TYPE_CHECKING:
    from shared.models.ais_message import PositionReport

logger = logging.getLogger("ais-ingest")


class BatchWriter:
    """Buffers positions and flushes in batches using asyncpg."""

    def __init__(
        self,
        dsn: str,
        redis_client,
        batch_size: int = 500,
        flush_interval: float = 2.0,
        metrics=None,
    ):
        self.dsn = dsn  # raw postgresql:// DSN (not async SQLAlchemy URL)
        self.redis = redis_client
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.metrics = metrics
        self._position_buffer: list[tuple] = []
        self._vessel_updates: dict[int, dict] = {}  # mmsi -> profile data
        self._pool: asyncpg.Pool | None = None
        self._flush_task: asyncio.Task | None = None
        self._flush_lock = asyncio.Lock()

    async def start(self):
        """Create connection pool and start periodic flush."""
        self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=3)
        self._flush_task = asyncio.create_task(self._periodic_flush())

    async def stop(self):
        """Flush remaining buffer and close pool."""
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush()  # final flush
        if self._pool:
            await self._pool.close()

    async def add_position(self, report: PositionReport):
        """Add a position to the buffer. Flushes if buffer reaches batch_size."""
        self._position_buffer.append((
            report.timestamp,
            report.mmsi,
            report.longitude,  # x
            report.latitude,   # y
            report.sog,
            report.cog,
            report.heading,
            report.nav_status,
            report.rot,
            None,  # draught (not in position report)
        ))
        if len(self._position_buffer) >= self.batch_size:
            try:
                await self._flush()
            except Exception:
                logger.exception("Batch-size flush failed")

    async def add_vessel_update(self, mmsi: int, static_data: dict):
        """Queue a vessel profile update."""
        self._vessel_updates[mmsi] = static_data

    async def _periodic_flush(self):
        """Flush buffer every flush_interval seconds."""
        while True:
            await asyncio.sleep(self.flush_interval)
            if self._position_buffer:
                try:
                    await self._flush()
                except Exception:
                    logger.exception("Periodic flush failed, will retry next cycle")

    async def _flush(self):
        """Flush position buffer and vessel updates to database."""
        async with self._flush_lock:
            await self._flush_locked()

    async def _flush_locked(self):
        """Flush implementation — must be called under _flush_lock."""
        if not self._position_buffer and not self._vessel_updates:
            return

        positions = self._position_buffer[:]
        vessels = dict(self._vessel_updates)
        self._position_buffer.clear()
        self._vessel_updates.clear()

        mmsis = list(set(t[1] for t in positions))

        # Write to database — if this fails, data is lost from the buffer
        # but the service stays alive to process new messages
        try:
            async with self._pool.acquire() as conn:
                if positions:
                    await conn.executemany(
                        """INSERT INTO vessel_positions
                           (timestamp, mmsi, position, sog, cog, heading,
                            nav_status, rot, draught)
                           VALUES ($1, $2,
                                   ST_SetSRID(ST_MakePoint($3, $4), 4326)::geography,
                                   $5, $6, $7, $8, $9, $10)""",
                        positions,
                    )

                    # Deduplicate to latest position per MMSI
                    latest: dict[int, tuple] = {}
                    for p in positions:
                        mmsi = p[1]
                        if mmsi not in latest or p[0] > latest[mmsi][0]:
                            latest[mmsi] = p

                    await conn.executemany(
                        """INSERT INTO vessel_profiles
                               (mmsi, last_position_time, last_lat, last_lon,
                                last_sog, last_cog, last_heading, updated_at)
                           VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                           ON CONFLICT (mmsi) DO UPDATE SET
                             last_position_time = EXCLUDED.last_position_time,
                             last_lat = EXCLUDED.last_lat,
                             last_lon = EXCLUDED.last_lon,
                             last_sog = EXCLUDED.last_sog,
                             last_cog = EXCLUDED.last_cog,
                             last_heading = EXCLUDED.last_heading,
                             updated_at = NOW()""",
                        [
                            (p[1], p[0], p[3], p[2], p[4], p[5], p[6])
                            # mmsi, timestamp, lat, lon, sog, cog, heading
                            for p in latest.values()
                        ],
                    )

                for mmsi, data in vessels.items():
                    data["mmsi"] = mmsi

                    # --- Profile overwrite protection ---
                    # Don't let AIS updates from transponders without IMO
                    # overwrite identity fields on profiles that have a valid IMO.
                    # This is a belt-and-suspenders guard behind the collision
                    # detection in main.py.
                    _IDENTITY_FIELDS = frozenset({
                        "ship_name", "call_sign", "ship_type", "length",
                        "width", "draught", "destination",
                    })
                    has_imo = bool(data.get("imo"))

                    cols = list(data.keys())
                    vals = [data[c] for c in cols]
                    placeholders = [f"${i + 1}" for i in range(len(cols))]
                    updates = []
                    for c in cols:
                        if c == "mmsi":
                            continue
                        if c in _IDENTITY_FIELDS and not has_imo:
                            # Only overwrite identity fields if the incoming
                            # data has an IMO (trusted source), OR the existing
                            # profile has no IMO yet.
                            updates.append(
                                f"{c} = CASE"
                                f" WHEN vessel_profiles.imo IS NULL"
                                f"  THEN COALESCE(EXCLUDED.{c}, vessel_profiles.{c})"
                                f" ELSE vessel_profiles.{c}"
                                f" END"
                            )
                        else:
                            updates.append(
                                f"{c} = COALESCE(EXCLUDED.{c}, vessel_profiles.{c})"
                            )
                    updates.append("updated_at = NOW()")

                    sql = (
                        f"INSERT INTO vessel_profiles ({', '.join(cols)})"
                        f" VALUES ({', '.join(placeholders)})"
                        f" ON CONFLICT (mmsi) DO UPDATE SET {', '.join(updates)}"
                    )
                    await conn.execute(sql, *vals)
        except Exception:
            logger.exception("Database flush failed (%d positions, %d vessels)", len(positions), len(vessels))
            return  # skip Redis publish — nothing was persisted

        # Publish positions to Redis for WebSocket clients (if Redis available)
        if positions and self.redis:
            latest: dict[int, tuple] = {}
            for p in positions:
                latest[p[1]] = p  # p[1] = mmsi

            for p in latest.values():
                pos_event = _json_dumps({
                    "mmsi": p[1],
                    "lat": p[3],      # latitude (y)
                    "lon": p[2],      # longitude (x)
                    "sog": p[4],
                    "cog": p[5],
                    "heading": p[6],
                    "nav_status": p[7],
                    "timestamp": p[0].isoformat() if hasattr(p[0], 'isoformat') else str(p[0]),
                    "risk_tier": "green",
                    "risk_score": 0,
                })
                try:
                    await self.redis.publish("heimdal:positions", pos_event)
                except Exception:
                    logger.warning("Redis publish failed for MMSI %d", p[1])
                    break  # don't spam logs if Redis is down

        if positions and self.metrics:
            try:
                await self.metrics.record_batch(len(positions), mmsis)
            except Exception:
                logger.warning("Metrics recording failed")
