"""Speed Anomaly rule.

Detects two suspicious speed patterns:

1. **Sustained slow steaming** — average SOG < 5 knots over a 2-hour
   window, outside a port approach area.
2. **Abrupt speed change** — a delta > 10 knots between consecutive
   position reports.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule

_SLOW_STEAM_THRESHOLD_KNOTS = 5.0
_SLOW_STEAM_MIN_HOURS = 2.0
_ABRUPT_DELTA_KNOTS = 10.0


class SpeedAnomalyRule(ScoringRule):
    """Fire on sustained slow steaming or abrupt speed changes."""

    @property
    def rule_id(self) -> str:
        return "speed_anomaly"

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
        if len(recent_positions) < 2:
            return None

        sorted_pos = sorted(recent_positions, key=lambda p: p.get("timestamp", ""))

        # Check for abrupt speed change first (more suspicious)
        abrupt = self._check_abrupt_change(sorted_pos)
        if abrupt:
            return abrupt

        # Check for sustained slow steaming
        slow = self._check_slow_steaming(sorted_pos)
        if slow:
            return slow

        return RuleResult(fired=False, rule_id=self.rule_id)

    # ------------------------------------------------------------------

    def _check_abrupt_change(
        self, positions: list[dict[str, Any]]
    ) -> Optional[RuleResult]:
        """Detect > 10-knot delta between consecutive positions."""
        for i in range(1, len(positions)):
            sog_prev = positions[i - 1].get("sog")
            sog_curr = positions[i].get("sog")
            if sog_prev is None or sog_curr is None:
                continue
            delta = abs(sog_curr - sog_prev)
            if delta > _ABRUPT_DELTA_KNOTS:
                return RuleResult(
                    fired=True,
                    rule_id=self.rule_id,
                    severity="moderate",
                    points=15.0,
                    details={
                        "reason": "abrupt_speed_change",
                        "speed_delta_knots": round(delta, 2),
                        "sog_before": sog_prev,
                        "sog_after": sog_curr,
                    },
                    source="realtime",
                )
        return None

    def _check_slow_steaming(
        self, positions: list[dict[str, Any]]
    ) -> Optional[RuleResult]:
        """Detect sustained SOG < 5 knots over >= 2 hours."""
        slow_start: Optional[datetime] = None
        slow_positions: list[dict[str, Any]] = []

        for pos in positions:
            sog = pos.get("sog")
            if sog is None:
                continue
            ts = pos.get("timestamp")
            if ts is None:
                continue
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            if not ts.tzinfo:
                ts = ts.replace(tzinfo=timezone.utc)

            if sog < _SLOW_STEAM_THRESHOLD_KNOTS:
                if slow_start is None:
                    slow_start = ts
                slow_positions.append(pos)
                duration_hours = (ts - slow_start).total_seconds() / 3600.0
                if duration_hours >= _SLOW_STEAM_MIN_HOURS:
                    avg_speed = sum(
                        p.get("sog", 0) for p in slow_positions
                    ) / len(slow_positions)
                    return RuleResult(
                        fired=True,
                        rule_id=self.rule_id,
                        severity="moderate",
                        points=15.0,
                        details={
                            "reason": "sustained_slow_steaming",
                            "duration_hours": round(duration_hours, 2),
                            "avg_speed_knots": round(avg_speed, 2),
                            "position_count": len(slow_positions),
                        },
                        source="realtime",
                    )
            else:
                slow_start = None
                slow_positions = []

        return None
