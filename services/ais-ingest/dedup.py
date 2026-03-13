"""Redis-based deduplication for AIS messages.

Uses SET NX EX to ensure each (MMSI, timestamp) pair is processed only once
within a short TTL window.
"""

from __future__ import annotations

from datetime import datetime

from redis.asyncio import Redis


class Deduplicator:
    """Check-and-set deduplication using Redis NX + TTL."""

    DEDUP_TTL_SECONDS = 10
    KEY_PREFIX = "heimdal:dedup"

    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    async def is_duplicate(self, mmsi: int, timestamp: datetime) -> bool:
        """Check if this (mmsi, timestamp) has been seen recently.

        Sets the key atomically with NX + EX. Returns True if the key
        already existed (i.e., this is a duplicate).
        """
        ts_rounded = timestamp.replace(microsecond=0).isoformat()
        key = f"{self.KEY_PREFIX}:{mmsi}:{ts_rounded}"
        # SET NX EX: set only if not exists, expire in TTL seconds
        result = await self.redis.set(
            key, "1", nx=True, ex=self.DEDUP_TTL_SECONDS
        )
        # result is True if key was set (new), None if key already existed (duplicate)
        return result is None

    async def filter_duplicates_batch(
        self, messages: list[tuple[int, datetime]]
    ) -> list[bool]:
        """Check a batch of (mmsi, timestamp) pairs in a single Redis pipeline.

        Returns a list of booleans: True = new (not duplicate), False = duplicate.
        Uses Redis pipelining to perform all SET NX EX operations in a single
        round-trip, which is significantly faster than individual calls.
        """
        if not messages:
            return []

        keys = []
        for mmsi, timestamp in messages:
            ts_rounded = timestamp.replace(microsecond=0).isoformat()
            keys.append(f"{self.KEY_PREFIX}:{mmsi}:{ts_rounded}")

        async with self.redis.pipeline() as pipe:
            for key in keys:
                pipe.set(key, "1", nx=True, ex=self.DEDUP_TTL_SECONDS)
            results = await pipe.execute()

        # result is True if key was set (new), None/False if existed (duplicate)
        return [r is not None and r is not False for r in results]
