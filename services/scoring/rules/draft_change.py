"""Draft Change Detection rule.

Detects significant draught increases while a vessel is anchored or
drifting at sea (not near a port/terminal), which may indicate an
unreported ship-to-ship transfer.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule

# Minimum draught increase to trigger (metres)
_MIN_DRAUGHT_INCREASE_M = 2.0

# Tolerance for draught return-to-normal check (metres)
_DRAUGHT_RETURN_TOLERANCE_M = 0.5

# Navigation statuses indicating anchored (1) or moored (5)
_ANCHORED_NAV_STATUSES = {1, 5}

# Maximum SOG to consider "stationary"
_MAX_SOG_KNOTS = 1.0


class DraftChangeRule(ScoringRule):
    """Fire on significant draught increase while anchored/drifting at sea."""

    @property
    def rule_id(self) -> str:
        return "draft_change"

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

        # Find the earliest and latest draught values
        draughts = [
            (p.get("draught"), p)
            for p in sorted_pos
            if p.get("draught") is not None
        ]
        if len(draughts) < 2:
            return None

        earliest_draught, _ = draughts[0]
        latest_draught, latest_pos = draughts[-1]
        increase = latest_draught - earliest_draught

        if increase < _MIN_DRAUGHT_INCREASE_M:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Check if vessel is anchored/drifting (nav_status and low SOG)
        nav_status = latest_pos.get("nav_status")
        sog = latest_pos.get("sog", 0.0)

        is_stationary = (
            nav_status in _ANCHORED_NAV_STATUSES
            or (sog is not None and sog < _MAX_SOG_KNOTS)
        )
        if not is_stationary:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Check if near a terminal (port) — if so, don't fire
        is_near_port = await self._check_near_terminal(latest_pos)
        if is_near_port:
            return RuleResult(fired=False, rule_id=self.rule_id)

        return RuleResult(
            fired=True,
            rule_id=self.rule_id,
            severity="high",
            points=40.0,
            details={
                "draught_increase_m": round(increase, 2),
                "earliest_draught": earliest_draught,
                "latest_draught": latest_draught,
                "nav_status": nav_status,
                "sog": sog,
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
        """End when draught returns to within 0.5m of the earliest draught value."""
        details = active_anomaly.get("details", {})
        if isinstance(details, str):
            import json
            details = json.loads(details)
        earliest_draught = details.get("earliest_draught")
        if earliest_draught is None:
            return False

        # Get the latest draught from recent positions
        sorted_pos = sorted(recent_positions, key=lambda p: p.get("timestamp", ""))
        for pos in reversed(sorted_pos):
            draught = pos.get("draught")
            if draught is not None:
                return abs(draught - earliest_draught) <= _DRAUGHT_RETURN_TOLERANCE_M
        return False

    # ------------------------------------------------------------------

    @staticmethod
    async def _check_near_terminal(pos: dict[str, Any]) -> bool:
        """Check if the position is near a known terminal/port."""
        lat, lon = pos.get("lat"), pos.get("lon")
        if lat is None or lon is None:
            return False
        return await _check_near_terminal_db(lat, lon)


async def _check_near_terminal_db(lat: float, lon: float) -> bool:
    """DB-backed terminal check.  Extracted so tests can patch this function."""
    from shared.db.connection import get_session
    from .zone_helpers import is_near_russian_terminal

    async with get_session() as session:
        result = await is_near_russian_terminal(session, lat, lon)
        return result is not None
