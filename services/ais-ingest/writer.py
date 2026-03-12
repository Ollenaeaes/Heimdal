"""Batch writer for AIS positions and vessel profiles.

Buffers position reports and flushes in batches using asyncpg executemany
with PostGIS ST_MakePoint. Publishes flush events to Redis.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
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
    ):
        self.dsn = dsn  # raw postgresql:// DSN (not async SQLAlchemy URL)
        self.redis = redis_client
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._position_buffer: list[tuple] = []
        self._vessel_updates: dict[int, dict] = {}  # mmsi -> profile data
        self._pool: asyncpg.Pool | None = None
        self._flush_task: asyncio.Task | None = None

    async def start(self):
        """Create connection pool and start periodic flush."""
        self._pool = await asyncpg.create_pool(self.dsn, min_size=2, max_size=10)
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
            await self._flush()

    async def add_vessel_update(self, mmsi: int, static_data: dict):
        """Queue a vessel profile update."""
        self._vessel_updates[mmsi] = static_data

    async def _periodic_flush(self):
        """Flush buffer every flush_interval seconds."""
        while True:
            await asyncio.sleep(self.flush_interval)
            if self._position_buffer:
                await self._flush()

    async def _flush(self):
        """Flush position buffer and vessel updates to database."""
        if not self._position_buffer and not self._vessel_updates:
            return

        positions = self._position_buffer[:]
        vessels = dict(self._vessel_updates)
        self._position_buffer.clear()
        self._vessel_updates.clear()

        mmsis = list(set(t[1] for t in positions))

        async with self._pool.acquire() as conn:
            # Insert positions using executemany (COPY not practical with PostGIS)
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

                # Update last_position_at for each vessel
                for pos_tuple in positions:
                    await conn.execute(
                        """UPDATE vessel_profiles
                           SET last_position_time = $1,
                               last_lat = $2,
                               last_lon = $3,
                               updated_at = NOW()
                           WHERE mmsi = $4""",
                        pos_tuple[0],  # timestamp
                        pos_tuple[3],  # latitude (y)
                        pos_tuple[2],  # longitude (x)
                        pos_tuple[1],  # mmsi
                    )

            # Upsert vessel profiles
            for mmsi, data in vessels.items():
                data["mmsi"] = mmsi
                cols = list(data.keys())
                vals = [data[c] for c in cols]
                placeholders = [f"${i + 1}" for i in range(len(cols))]
                updates = [
                    f"{c} = COALESCE(EXCLUDED.{c}, vessel_profiles.{c})"
                    for c in cols
                    if c != "mmsi"
                ]
                updates.append("updated_at = NOW()")

                sql = (
                    f"INSERT INTO vessel_profiles ({', '.join(cols)})"
                    f" VALUES ({', '.join(placeholders)})"
                    f" ON CONFLICT (mmsi) DO UPDATE SET {', '.join(updates)}"
                )
                await conn.execute(sql, *vals)

        # Publish to Redis
        if positions:
            event = json.dumps({
                "mmsis": mmsis,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "count": len(positions),
            })
            await self.redis.publish("heimdal:positions", event)
