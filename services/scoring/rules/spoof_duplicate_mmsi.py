"""Spoofing detection: duplicate MMSI from distant locations.

Fires when the same MMSI is received within 5 minutes from positions
more than 10 nautical miles apart, indicating two different vessels
are transmitting the same MMSI.

Uses Redis to track the last known position per MMSI.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .ais_spoofing import haversine_nm
from .base import ScoringRule

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_TIME_DELTA_SECONDS = 300  # 5 minutes
_MIN_DISTANCE_NM = 10.0       # 10 nautical miles
_REDIS_KEY_PREFIX = "heimdal:last_pos"
_REDIS_TTL_SECONDS = 600      # 10 minutes


def _parse_ts(ts: Any) -> Optional[datetime]:
    """Parse a timestamp into a timezone-aware datetime."""
    if ts is None:
        return None
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    return None


class SpoofDuplicateMmsiRule(ScoringRule):
    """Fire when the same MMSI appears simultaneously in distant locations."""

    def __init__(self, redis_client: Any = None):
        self._redis = redis_client

    @property
    def rule_id(self) -> str:
        return "spoof_duplicate_mmsi"

    @property
    def rule_category(self) -> str:
        return "realtime"

    def _get_redis(self) -> Any:
        """Get the Redis client, lazily importing if not injected."""
        if self._redis is not None:
            return self._redis
        try:
            import redis
            from shared.config import settings
            redis_url = getattr(settings, "redis_url", "redis://localhost:6379")
            if hasattr(redis_url, "get_secret_value"):
                redis_url = redis_url.get_secret_value()
            self._redis = redis.Redis.from_url(str(redis_url))
            return self._redis
        except Exception:
            logger.warning("Redis unavailable — spoof_duplicate_mmsi disabled")
            return None

    async def evaluate(
        self,
        mmsi: int,
        profile: dict[str, Any] | None,
        recent_positions: Sequence[dict[str, Any]],
        existing_anomalies: Sequence[dict[str, Any]],
        gfw_events: Sequence[dict[str, Any]],
    ) -> Optional[RuleResult]:
        if not recent_positions:
            return None

        redis_client = self._get_redis()
        if redis_client is None:
            return None

        # Use the latest position
        latest = max(recent_positions, key=lambda p: p.get("timestamp", ""))
        lat = latest.get("lat")
        lon = latest.get("lon")
        ts = _parse_ts(latest.get("timestamp"))

        if lat is None or lon is None or ts is None:
            return None

        redis_key = f"{_REDIS_KEY_PREFIX}:{mmsi}"

        # Get previous position from Redis
        prev_data = redis_client.get(redis_key)

        # Store current position in Redis (always update)
        current_data = json.dumps({
            "lat": lat,
            "lon": lon,
            "timestamp": ts.isoformat(),
        })
        redis_client.setex(redis_key, _REDIS_TTL_SECONDS, current_data)

        # First-ever position for this MMSI → do not fire
        if prev_data is None:
            return RuleResult(fired=False, rule_id=self.rule_id)

        try:
            prev = json.loads(prev_data)
        except (json.JSONDecodeError, TypeError):
            return RuleResult(fired=False, rule_id=self.rule_id)

        prev_lat = prev.get("lat")
        prev_lon = prev.get("lon")
        prev_ts = _parse_ts(prev.get("timestamp"))

        if prev_lat is None or prev_lon is None or prev_ts is None:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Check time delta
        time_delta = abs((ts - prev_ts).total_seconds())
        if time_delta > _MAX_TIME_DELTA_SECONDS:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Check distance
        distance = haversine_nm(prev_lat, prev_lon, lat, lon)
        if distance <= _MIN_DISTANCE_NM:
            return RuleResult(fired=False, rule_id=self.rule_id)

        return RuleResult(
            fired=True,
            rule_id=self.rule_id,
            severity="critical",
            points=100.0,
            details={
                "reason": "duplicate_mmsi",
                "distance_nm": round(distance, 2),
                "time_delta_seconds": round(time_delta, 1),
                "prev_lat": prev_lat,
                "prev_lon": prev_lon,
                "curr_lat": lat,
                "curr_lon": lon,
            },
            source="realtime",
        )
