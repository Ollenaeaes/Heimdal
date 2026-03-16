"""Cable Alignment Transit rule.

Detects vessels whose course over ground (COG) is aligned with a
submarine cable or pipeline bearing for an extended period, which may
indicate the vessel is deliberately following the cable route.

Uses Redis state to track consecutive alignment across evaluation cycles.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule

logger = logging.getLogger("scoring.cable_alignment")

_ALIGNMENT_THRESHOLD_DEG = 20.0  # fire when within this angle
_RESET_THRESHOLD_DEG = 30.0  # reset when angle exceeds this
_MIN_DURATION_MINUTES = 15.0
_CRITICAL_DURATION_MINUTES = 60.0

# Redis key prefix
_REDIS_KEY_PREFIX = "heimdal:cable_align:"


def _utcnow() -> datetime:
    """Return current UTC time.  Extracted for easy patching in tests."""
    return datetime.now(timezone.utc)


class CableAlignmentRule(ScoringRule):
    """Fire when a vessel's COG aligns with cable bearing for extended time."""

    @property
    def rule_id(self) -> str:
        return "cable_alignment"

    @property
    def rule_category(self) -> str:
        return "realtime"

    # Service vessel types excluded from cable rules
    _SERVICE_VESSEL_TYPES = {31, 32, 33, 50, 51, 52, 53, 55, 56, 57, 58, 59}

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

        # Skip service vessels (tugs, pilots, SAR, cable layers)
        ship_type = (profile or {}).get("ship_type")
        if ship_type in self._SERVICE_VESSEL_TYPES:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Get latest position
        sorted_pos = sorted(
            recent_positions, key=lambda p: p.get("timestamp", "")
        )
        latest = sorted_pos[-1]
        lat = latest.get("lat")
        lon = latest.get("lon")
        cog = latest.get("cog")

        if lat is None or lon is None or cog is None:
            return None

        # Check infrastructure corridor
        routes = await self._check_corridor(lat, lon)
        if not routes:
            await self._clear_redis_state(mmsi)
            return RuleResult(fired=False, rule_id=self.rule_id)

        route = routes[0]

        # Compute cable bearing at this position
        cable_bearing = await self._get_cable_bearing(lat, lon, route["id"])
        if cable_bearing is None:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Check alignment (must account for cable going in either direction)
        from .infra_helpers import angle_difference

        angle_diff = angle_difference(cog, cable_bearing)

        now = _utcnow()
        state = await self._get_redis_state(mmsi)

        if angle_diff <= _ALIGNMENT_THRESHOLD_DEG:
            # Vessel is aligned
            if state is None:
                # First detection
                await self._set_redis_state(mmsi, {
                    "route_id": route["id"],
                    "first_parallel_time": now.isoformat(),
                    "consecutive_count": 1,
                })
                return RuleResult(fired=False, rule_id=self.rule_id)

            # Increment count
            first_parallel = datetime.fromisoformat(state["first_parallel_time"])
            if not first_parallel.tzinfo:
                first_parallel = first_parallel.replace(tzinfo=timezone.utc)
            duration_minutes = (now - first_parallel).total_seconds() / 60.0
            count = state.get("consecutive_count", 1) + 1

            await self._set_redis_state(mmsi, {
                "route_id": route["id"],
                "first_parallel_time": state["first_parallel_time"],
                "consecutive_count": count,
            })

            if duration_minutes < _MIN_DURATION_MINUTES:
                return RuleResult(fired=False, rule_id=self.rule_id)

            # Determine severity and points
            if duration_minutes >= _CRITICAL_DURATION_MINUTES:
                severity = "critical"
                points = 100.0
            else:
                severity = "high"
                points = 40.0

            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity=severity,
                points=points,
                details={
                    "reason": "cable_alignment_transit",
                    "route_name": route["name"],
                    "route_type": route["route_type"],
                    "route_id": route["id"],
                    "duration_minutes": round(duration_minutes, 1),
                    "angle_difference": round(angle_diff, 1),
                    "cable_bearing": round(cable_bearing, 1),
                    "cog": cog,
                    "consecutive_count": count,
                    "lat": lat,
                    "lon": lon,
                },
                source="realtime",
            )

        elif angle_diff > _RESET_THRESHOLD_DEG:
            # Vessel diverged — reset tracking
            await self._clear_redis_state(mmsi)
            return RuleResult(fired=False, rule_id=self.rule_id)
        else:
            # Between alignment and reset thresholds — maintain state
            return RuleResult(fired=False, rule_id=self.rule_id)

    async def check_event_ended(
        self,
        mmsi: int,
        profile: dict[str, Any] | None,
        recent_positions: Sequence[dict[str, Any]],
        active_anomaly: dict[str, Any],
    ) -> bool:
        """End when vessel's COG diverges from cable bearing (>30 degrees)."""
        if not recent_positions:
            return False
        sorted_pos = sorted(
            recent_positions, key=lambda p: p.get("timestamp", "")
        )
        latest = sorted_pos[-1]
        lat = latest.get("lat")
        lon = latest.get("lon")
        cog = latest.get("cog")

        if lat is None or lon is None or cog is None:
            return False

        # Check if still in corridor
        routes = await self._check_corridor(lat, lon)
        if not routes:
            await self._clear_redis_state(mmsi)
            return True

        route = routes[0]
        cable_bearing = await self._get_cable_bearing(lat, lon, route["id"])
        if cable_bearing is None:
            return False

        from .infra_helpers import angle_difference

        angle_diff = angle_difference(cog, cable_bearing)
        if angle_diff > _RESET_THRESHOLD_DEG:
            await self._clear_redis_state(mmsi)
            return True

        return False

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _check_corridor(lat: float, lon: float) -> list[dict]:
        """Check if position is in an infrastructure corridor."""
        from shared.db.connection import get_session
        from .infra_helpers import is_in_infrastructure_corridor

        session_factory = get_session()
        async with session_factory() as session:
            return await is_in_infrastructure_corridor(session, lat, lon)

    @staticmethod
    async def _get_cable_bearing(
        lat: float, lon: float, route_id: int
    ) -> Optional[float]:
        """Get the cable bearing at a given position."""
        from shared.db.connection import get_session
        from .infra_helpers import compute_cable_bearing

        session_factory = get_session()
        async with session_factory() as session:
            return await compute_cable_bearing(session, lat, lon, route_id)

    # ------------------------------------------------------------------
    # Redis state management
    # ------------------------------------------------------------------

    @staticmethod
    async def _get_redis_state(mmsi: int) -> Optional[dict]:
        """Get cable alignment state from Redis."""
        try:
            import redis.asyncio as aioredis
            from shared.config import settings

            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            try:
                data = await client.get(f"{_REDIS_KEY_PREFIX}{mmsi}")
                if data:
                    return json.loads(data)
                return None
            finally:
                await client.aclose()
        except Exception:
            logger.debug("Redis unavailable for cable_align state, mmsi=%d", mmsi)
            return None

    @staticmethod
    async def _set_redis_state(mmsi: int, state: dict) -> None:
        """Set cable alignment state in Redis with 24h TTL."""
        try:
            import redis.asyncio as aioredis
            from shared.config import settings

            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            try:
                await client.set(
                    f"{_REDIS_KEY_PREFIX}{mmsi}",
                    json.dumps(state),
                    ex=86400,
                )
            finally:
                await client.aclose()
        except Exception:
            logger.debug("Redis unavailable for cable_align state, mmsi=%d", mmsi)

    @staticmethod
    async def _clear_redis_state(mmsi: int) -> None:
        """Clear cable alignment state from Redis."""
        try:
            import redis.asyncio as aioredis
            from shared.config import settings

            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            try:
                await client.delete(f"{_REDIS_KEY_PREFIX}{mmsi}")
            finally:
                await client.aclose()
        except Exception:
            logger.debug("Redis unavailable for cable_align state, mmsi=%d", mmsi)
