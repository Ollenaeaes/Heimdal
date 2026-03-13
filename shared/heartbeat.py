"""Service heartbeat publisher for health monitoring.

Each Heimdal service publishes a periodic heartbeat to Redis so the API
health endpoint can report whether services are alive, degraded, or down.

Redis key pattern: ``heimdal:heartbeat:{service_name}``
Value: JSON string with service name, timestamp, uptime, and service-specific metrics.
TTL: 120 seconds (heartbeat published every 60 seconds, so a missed beat
     leaves a 60-second grace window before the key expires).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("heimdal.heartbeat")

# Redis key prefix for heartbeat entries
HEARTBEAT_KEY_PREFIX = "heimdal:heartbeat:"

# Well-known service names
SERVICES = ("ais-ingest", "scoring", "enrichment")


class HeartbeatPublisher:
    """Publishes periodic heartbeat messages to Redis for a single service.

    Parameters
    ----------
    redis_client:
        An ``redis.asyncio`` client instance.
    service_name:
        Identifier written into the heartbeat payload and used as the Redis
        key suffix (e.g. ``"ais-ingest"``).
    interval:
        Seconds between heartbeat publishes.  Default ``60``.
    ttl:
        TTL applied to the Redis key, in seconds.  Default ``120``.
    """

    def __init__(
        self,
        redis_client: Any,
        service_name: str,
        interval: int = 60,
        ttl: int = 120,
    ) -> None:
        self._redis = redis_client
        self._service_name = service_name
        self._interval = interval
        self._ttl = ttl
        self._metrics: dict[str, Any] = {}
        self._task: asyncio.Task[None] | None = None
        self._start_time: float = time.monotonic()
        self._stopped = False

    # -- public helpers -----------------------------------------------------

    @property
    def redis_key(self) -> str:
        return f"{HEARTBEAT_KEY_PREFIX}{self._service_name}"

    def update_metric(self, key: str, value: Any) -> None:
        """Update a service-specific metric included in the next heartbeat."""
        self._metrics[key] = value

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        """Start the background heartbeat loop."""
        if self._task is not None:
            return
        self._start_time = time.monotonic()
        self._stopped = False
        self._task = asyncio.create_task(self._loop())
        logger.info("Heartbeat started for %s (interval=%ds, ttl=%ds)",
                     self._service_name, self._interval, self._ttl)

    async def stop(self) -> None:
        """Cancel the background heartbeat loop and wait for it to finish."""
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Heartbeat stopped for %s", self._service_name)

    # -- internals ----------------------------------------------------------

    def _build_payload(self) -> str:
        uptime = time.monotonic() - self._start_time
        payload: dict[str, Any] = {
            "service": self._service_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": round(uptime, 1),
        }
        payload.update(self._metrics)
        return json.dumps(payload)

    async def _publish_once(self) -> None:
        payload = self._build_payload()
        await self._redis.set(self.redis_key, payload, ex=self._ttl)

    async def _loop(self) -> None:
        try:
            while not self._stopped:
                try:
                    await self._publish_once()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Failed to publish heartbeat for %s",
                                     self._service_name)
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            pass
