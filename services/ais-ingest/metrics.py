"""Metrics publisher for AIS ingest pipeline.

Tracks ingestion rate, last message time, and unique vessel count,
publishing to Redis for dashboard consumption.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from redis.asyncio import Redis


class MetricsPublisher:
    """Publishes ingest metrics to Redis."""

    RATE_KEY = "heimdal:metrics:ingest_rate"
    LAST_MESSAGE_KEY = "heimdal:metrics:last_message_at"
    VESSELS_KEY = "heimdal:metrics:total_vessels"
    WINDOW_SECONDS = 60

    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client
        self._positions_window: list[tuple[float, int]] = []
        self._unique_mmsis: set[int] = set()

    async def record_batch(self, count: int, mmsis: list[int]) -> None:
        """Record a flushed batch for metrics.

        Args:
            count: Number of positions in the batch.
            mmsis: List of MMSIs in the batch.
        """
        now = time.time()
        self._positions_window.append((now, count))
        self._unique_mmsis.update(mmsis)

        # Prune window to last WINDOW_SECONDS
        cutoff = now - self.WINDOW_SECONDS
        self._positions_window = [
            (t, c) for t, c in self._positions_window if t > cutoff
        ]

        # Calculate rate (positions per second)
        total = sum(c for _, c in self._positions_window)
        if self._positions_window:
            elapsed = max(now - self._positions_window[0][0], 1)
        else:
            elapsed = 1
        rate = total / elapsed

        # Publish to Redis — rate key expires if no batches arrive
        await self.redis.set(self.RATE_KEY, f"{rate:.1f}", ex=self.WINDOW_SECONDS * 2)
        await self.redis.set(
            self.LAST_MESSAGE_KEY,
            datetime.now(timezone.utc).isoformat(),
        )
        await self.redis.set(
            self.VESSELS_KEY, str(len(self._unique_mmsis))
        )
