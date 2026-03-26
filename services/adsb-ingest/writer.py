"""Batch writer for ADS-B positions of aircraft of interest.

Buffers position reports and flushes in batches using asyncpg.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import asyncpg

logger = logging.getLogger("adsb-ingest.writer")


class AdsbBatchWriter:
    """Buffers ADS-B positions and flushes in batches."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        batch_size: int = 200,
        flush_interval: float = 5.0,
    ):
        self._pool = pool
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._buffer: list[tuple] = []
        self._flush_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self._flush_task = asyncio.create_task(self._periodic_flush())

    async def stop(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush()

    def add_position(
        self,
        ac: dict,
        category: str | None = None,
        country: str | None = None,
        role: str | None = None,
    ) -> None:
        """Add an aircraft position to the buffer.

        `ac` is a raw adsb.lol aircraft dict.
        `category`, `country`, `role` are from the aircraft_of_interest lookup.
        """
        lat = ac.get("lat")
        lon = ac.get("lon")
        if lat is None or lon is None:
            return

        hex_code = ac.get("hex", "").lower()
        if not hex_code:
            return

        # Parse alt_baro — can be int or "ground"
        alt_baro = ac.get("alt_baro")
        if isinstance(alt_baro, str):
            alt_baro = None if alt_baro == "ground" else None

        ts = datetime.now(timezone.utc)

        self._buffer.append((
            ts,
            hex_code,
            (ac.get("flight") or "").strip() or None,
            lat,
            lon,
            alt_baro,
            ac.get("alt_geom"),
            ac.get("gs"),
            ac.get("track"),
            ac.get("baro_rate") or ac.get("geom_rate"),
            ac.get("squawk"),
            ac.get("nac_p"),
            ac.get("nic"),
            ac.get("alt_baro") == "ground",
            category,
            country,
            role,
        ))

        if len(self._buffer) >= self.batch_size:
            asyncio.create_task(self._flush())

    async def _periodic_flush(self) -> None:
        while True:
            await asyncio.sleep(self.flush_interval)
            if self._buffer:
                await self._flush()

    async def _flush(self) -> None:
        async with self._lock:
            if not self._buffer:
                return
            batch = self._buffer[:]
            self._buffer.clear()

        try:
            async with self._pool.acquire() as conn:
                await conn.executemany(
                    """INSERT INTO adsb_positions
                       (time, icao_hex, callsign, lat, lon,
                        alt_baro, alt_geom, ground_speed, track,
                        vertical_rate, squawk, nac_p, nic, on_ground,
                        category, country, role)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
                               $10, $11, $12, $13, $14, $15, $16, $17)""",
                    batch,
                )
            logger.debug("Flushed %d ADS-B positions", len(batch))
        except Exception:
            logger.exception("Failed to flush %d ADS-B positions", len(batch))
