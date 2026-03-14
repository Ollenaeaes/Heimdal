"""Cable Corridor Slow Transit rule.

Detects vessels lingering at slow speed within an infrastructure cable
corridor for an extended period, which may indicate anchor-dragging,
loitering, or sabotage preparation.

Uses Redis state to track corridor entry/exit across evaluation cycles.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule

logger = logging.getLogger("scoring.cable_slow_transit")

_SPEED_THRESHOLD_KNOTS = 7.0
_MIN_DURATION_MINUTES = 30.0
_CRITICAL_DURATION_MINUTES = 60.0
_CABLE_LAYER_SHIP_TYPE = 33  # cable-laying vessel

# Shadow fleet rule IDs that trigger escalation
_SHADOW_FLEET_RULE_IDS = frozenset({
    "sanctions_match",
    "gfw_port_visit",
    "flag_hopping",
    "insurance_class_risk",
})
_SHADOW_ESCALATION_POINTS = 40.0

# Redis key prefix
_REDIS_KEY_PREFIX = "heimdal:cable_entry:"


def _utcnow() -> datetime:
    """Return current UTC time.  Extracted for easy patching in tests."""
    return datetime.now(timezone.utc)


class CableSlowTransitRule(ScoringRule):
    """Fire when a vessel loiters at slow speed in a cable corridor."""

    @property
    def rule_id(self) -> str:
        return "cable_slow_transit"

    @property
    def rule_category(self) -> str:
        return "realtime"

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

        # Skip cable-laying vessels
        ship_type = (profile or {}).get("ship_type")
        if ship_type == _CABLE_LAYER_SHIP_TYPE:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Get latest position
        sorted_pos = sorted(
            recent_positions, key=lambda p: p.get("timestamp", "")
        )
        latest = sorted_pos[-1]
        lat = latest.get("lat")
        lon = latest.get("lon")
        sog = latest.get("sog")

        if lat is None or lon is None or sog is None:
            return None

        # Check infrastructure corridor
        routes = await self._check_corridor(lat, lon)
        if not routes:
            # Vessel not in corridor — clear Redis state
            await self._clear_redis_state(mmsi)
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Check port approach exclusion
        if await self._check_port_approach(lat, lon):
            await self._clear_redis_state(mmsi)
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Check speed threshold
        if sog >= _SPEED_THRESHOLD_KNOTS:
            await self._clear_redis_state(mmsi)
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Vessel is slow in corridor — track entry time
        route = routes[0]
        now = _utcnow()
        entry_data = await self._get_redis_state(mmsi)

        if entry_data is None:
            # First detection — record entry
            await self._set_redis_state(mmsi, {
                "route_id": route["id"],
                "entry_time": now.isoformat(),
                "entry_lat": lat,
                "entry_lon": lon,
            })
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Calculate duration since entry
        entry_time = datetime.fromisoformat(entry_data["entry_time"])
        if not entry_time.tzinfo:
            entry_time = entry_time.replace(tzinfo=timezone.utc)
        duration_minutes = (now - entry_time).total_seconds() / 60.0

        if duration_minutes < _MIN_DURATION_MINUTES:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Determine severity and points
        if duration_minutes >= _CRITICAL_DURATION_MINUTES:
            severity = "critical"
            points = 100.0
        else:
            severity = "high"
            points = 40.0

        # Shadow fleet escalation
        shadow_match = self._check_shadow_fleet(existing_anomalies)
        if shadow_match:
            points += _SHADOW_ESCALATION_POINTS

        return RuleResult(
            fired=True,
            rule_id=self.rule_id,
            severity=severity,
            points=points,
            details={
                "reason": "cable_corridor_slow_transit",
                "route_name": route["name"],
                "route_type": route["route_type"],
                "route_id": route["id"],
                "duration_minutes": round(duration_minutes, 1),
                "sog": sog,
                "lat": lat,
                "lon": lon,
                "shadow_fleet_escalation": shadow_match,
            },
            source="realtime",
        )

    async def check_event_ended(
        self,
        mmsi: int,
        profile: dict[str, Any] | None,
        recent_positions: Sequence[dict[str, Any]],
        active_anomaly: dict[str, Any],
    ) -> bool:
        """End when vessel exits corridor or speeds up above threshold."""
        if not recent_positions:
            return False
        sorted_pos = sorted(
            recent_positions, key=lambda p: p.get("timestamp", "")
        )
        latest = sorted_pos[-1]
        lat = latest.get("lat")
        lon = latest.get("lon")
        sog = latest.get("sog")

        if lat is None or lon is None:
            return False

        # End if vessel left corridor
        routes = await self._check_corridor(lat, lon)
        if not routes:
            await self._clear_redis_state(mmsi)
            return True

        # End if vessel sped up
        if sog is not None and sog >= _SPEED_THRESHOLD_KNOTS:
            await self._clear_redis_state(mmsi)
            return True

        return False

    # ------------------------------------------------------------------
    # DB helpers (extracted for test patching)
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
    async def _check_port_approach(lat: float, lon: float) -> bool:
        """Check if position is in a port approach zone."""
        from shared.db.connection import get_session
        from .infra_helpers import is_in_port_approach

        session_factory = get_session()
        async with session_factory() as session:
            return await is_in_port_approach(session, lat, lon)

    @staticmethod
    def _check_shadow_fleet(
        existing_anomalies: Sequence[dict[str, Any]],
    ) -> bool:
        """Check if existing anomalies include shadow fleet indicators."""
        for anomaly in existing_anomalies:
            rule_id = anomaly.get("rule_id", "")
            if rule_id in _SHADOW_FLEET_RULE_IDS and not anomaly.get("resolved", False):
                return True
        return False

    # ------------------------------------------------------------------
    # Redis state management
    # ------------------------------------------------------------------

    @staticmethod
    async def _get_redis_state(mmsi: int) -> Optional[dict]:
        """Get cable entry state from Redis."""
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
            logger.debug("Redis unavailable for cable_entry state, mmsi=%d", mmsi)
            return None

    @staticmethod
    async def _set_redis_state(mmsi: int, state: dict) -> None:
        """Set cable entry state in Redis with 24h TTL."""
        try:
            import redis.asyncio as aioredis
            from shared.config import settings

            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            try:
                await client.set(
                    f"{_REDIS_KEY_PREFIX}{mmsi}",
                    json.dumps(state),
                    ex=86400,  # 24h TTL
                )
            finally:
                await client.aclose()
        except Exception:
            logger.debug("Redis unavailable for cable_entry state, mmsi=%d", mmsi)

    @staticmethod
    async def _clear_redis_state(mmsi: int) -> None:
        """Clear cable entry state from Redis."""
        try:
            import redis.asyncio as aioredis
            from shared.config import settings

            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            try:
                await client.delete(f"{_REDIS_KEY_PREFIX}{mmsi}")
            finally:
                await client.aclose()
        except Exception:
            logger.debug("Redis unavailable for cable_entry state, mmsi=%d", mmsi)
