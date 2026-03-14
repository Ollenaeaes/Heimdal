"""Open Water Speed Anomaly Near Infrastructure rule.

Detects vessels whose speed drops significantly (>50% below 2-hour average)
upon entering an infrastructure corridor, which may indicate suspicious
activity near cables or pipelines.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule

logger = logging.getLogger("scoring.infra_speed_anomaly")

_SPEED_DROP_PERCENT = 50.0
_MIN_HISTORY_HOURS = 2.0
_MIN_POSITIONS_FOR_AVERAGE = 4  # Need enough data for a meaningful average


def _utcnow() -> datetime:
    """Return current UTC time.  Extracted for easy patching in tests."""
    return datetime.now(timezone.utc)


class InfraSpeedAnomalyRule(ScoringRule):
    """Fire when vessel speed drops >50% of 2h average upon entering a corridor."""

    @property
    def rule_id(self) -> str:
        return "infra_speed_anomaly"

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
        if len(recent_positions) < _MIN_POSITIONS_FOR_AVERAGE:
            return None

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
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Check port approach exclusion
        if await self._check_port_approach(lat, lon):
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Compute 2-hour average speed from positions BEFORE the latest
        now = _utcnow()
        avg_speed, position_count = self._compute_2h_average(sorted_pos[:-1], now)

        if avg_speed is None or avg_speed <= 0:
            # Insufficient speed history
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Check for >50% speed drop
        drop_percent = ((avg_speed - sog) / avg_speed) * 100.0
        if drop_percent <= _SPEED_DROP_PERCENT:
            return RuleResult(fired=False, rule_id=self.rule_id)

        route = routes[0]
        return RuleResult(
            fired=True,
            rule_id=self.rule_id,
            severity="moderate",
            points=15.0,
            details={
                "reason": "speed_drop_near_infrastructure",
                "route_name": route["name"],
                "route_type": route["route_type"],
                "route_id": route["id"],
                "current_sog": round(sog, 1),
                "avg_speed_2h": round(avg_speed, 1),
                "speed_drop_percent": round(drop_percent, 1),
                "positions_in_average": position_count,
                "lat": lat,
                "lon": lon,
            },
            source="realtime",
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _compute_2h_average(
        positions: Sequence[dict[str, Any]],
        reference_time: datetime,
    ) -> tuple[Optional[float], int]:
        """Compute average SOG over available positions, requiring >= 2 hours of history.

        Returns (avg_speed, count) or (None, 0) if insufficient data.
        The positions must span at least 2 hours to be considered valid.
        """
        if not reference_time.tzinfo:
            reference_time = reference_time.replace(tzinfo=timezone.utc)

        speeds: list[float] = []
        earliest_ts: Optional[datetime] = None

        for pos in positions:
            ts = pos.get("timestamp")
            if ts is None:
                continue
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            if not ts.tzinfo:
                ts = ts.replace(tzinfo=timezone.utc)

            sog = pos.get("sog")
            if sog is not None:
                speeds.append(sog)
                if earliest_ts is None or ts < earliest_ts:
                    earliest_ts = ts

        if len(speeds) < _MIN_POSITIONS_FOR_AVERAGE:
            return None, 0

        # Verify the position history spans at least 2 hours
        if earliest_ts is not None:
            span_hours = (reference_time - earliest_ts).total_seconds() / 3600.0
            if span_hours < _MIN_HISTORY_HOURS:
                return None, 0

        return sum(speeds) / len(speeds), len(speeds)

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
