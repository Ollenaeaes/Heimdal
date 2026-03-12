"""STS Zone Proximity rule.

Detects vessels loitering near known ship-to-ship transfer zones at low
speed for an extended period.  Examines ``recent_positions`` for
consecutive slow-speed positions and checks proximity to STS zones via
the ``zone_helpers`` module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule

# Thresholds
_SPEED_THRESHOLD_KNOTS = 3.0
_MIN_DURATION_HOURS = 6.0
_BUFFER_NM = 10.0  # nautical miles — zone_helpers default


class StsProximityRule(ScoringRule):
    """Fire when a vessel lingers near an STS zone at low speed."""

    @property
    def rule_id(self) -> str:
        return "sts_proximity"

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

        # Find consecutive slow-speed positions
        slow_spans = self._find_slow_spans(recent_positions)

        for span in slow_spans:
            duration_hours = span["duration_hours"]
            if duration_hours < _MIN_DURATION_HOURS:
                continue

            # Check if any position in the span is near an STS zone
            zone_name = await self._check_sts_zone(span["positions"])
            if zone_name:
                return RuleResult(
                    fired=True,
                    rule_id=self.rule_id,
                    severity="moderate",
                    points=15.0,
                    details={
                        "zone_name": zone_name,
                        "duration_hours": round(duration_hours, 2),
                        "avg_speed": round(span["avg_speed"], 2),
                        "position_count": len(span["positions"]),
                    },
                    source="realtime",
                )

        return RuleResult(fired=False, rule_id=self.rule_id)

    # ------------------------------------------------------------------

    @staticmethod
    def _find_slow_spans(
        positions: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Group consecutive positions where SOG < threshold."""
        spans: list[dict[str, Any]] = []
        current_span: list[dict[str, Any]] = []

        sorted_pos = sorted(positions, key=lambda p: p.get("timestamp", ""))

        for pos in sorted_pos:
            sog = pos.get("sog")
            if sog is None:
                continue
            if sog < _SPEED_THRESHOLD_KNOTS:
                current_span.append(pos)
            else:
                if len(current_span) >= 2:
                    spans.append(_make_span(current_span))
                current_span = []

        # Flush remaining span
        if len(current_span) >= 2:
            spans.append(_make_span(current_span))

        return spans

    @staticmethod
    async def _check_sts_zone(
        positions: list[dict[str, Any]],
    ) -> Optional[str]:
        """Check if any position in the span is within 10 nm of an STS zone.

        Uses the DB-backed zone_helpers.  If the DB session cannot be
        obtained (e.g. in tests), this is expected to be mocked.
        """
        return await _check_sts_zone_db(positions)


async def _check_sts_zone_db(positions: list[dict[str, Any]]) -> Optional[str]:
    """DB-backed STS zone check.  Extracted so tests can patch this function."""
    from shared.database import get_session
    from .zone_helpers import is_in_sts_zone

    async with get_session() as session:
        for pos in positions:
            lat, lon = pos.get("lat"), pos.get("lon")
            if lat is None or lon is None:
                continue
            zone_name = await is_in_sts_zone(session, lat, lon)
            if zone_name:
                return zone_name
    return None


def _make_span(positions: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute summary statistics for a span of slow-speed positions."""
    timestamps: list[datetime] = []
    for p in positions:
        ts = p.get("timestamp")
        if isinstance(ts, datetime):
            timestamps.append(ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc))
        elif isinstance(ts, str):
            timestamps.append(datetime.fromisoformat(ts).replace(tzinfo=timezone.utc))

    duration = (max(timestamps) - min(timestamps)).total_seconds() / 3600.0 if timestamps else 0.0
    speeds = [p["sog"] for p in positions if p.get("sog") is not None]
    avg_speed = sum(speeds) / len(speeds) if speeds else 0.0

    return {
        "positions": positions,
        "duration_hours": duration,
        "avg_speed": avg_speed,
    }
