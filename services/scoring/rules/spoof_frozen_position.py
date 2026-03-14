"""Spoofing detection: frozen / box-pattern positions.

Detects two spoofing patterns:
1. **Frozen position** — identical lat, lon, COG, SOG for > 2 hours while
   not at anchor or moored.
2. **Box pattern** — positions oscillating between 2-4 coordinate pairs
   for > 1 hour.

Uses recent_positions from the scoring engine (no Redis needed).
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FROZEN_MIN_HOURS = 2.0
_BOX_MIN_HOURS = 1.0

# Tolerance for "identical" values
_POSITION_TOLERANCE_DEG = 0.001
_SPEED_TOLERANCE_KN = 0.1

# Max distinct coordinate pairs for box pattern
_BOX_MAX_DISTINCT_PAIRS = 4

# Nav statuses that indicate legitimate stationarity
_STATIONARY_NAV_STATUSES = frozenset({
    "Moored", "At anchor",
    1, 5,  # at anchor, moored (numeric AIS codes)
})


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


def _round_position(lat: float, lon: float) -> tuple[float, float]:
    """Round position to tolerance grid for grouping."""
    return (
        round(lat / _POSITION_TOLERANCE_DEG) * _POSITION_TOLERANCE_DEG,
        round(lon / _POSITION_TOLERANCE_DEG) * _POSITION_TOLERANCE_DEG,
    )


class SpoofFrozenPositionRule(ScoringRule):
    """Fire on frozen or box-pattern AIS positions."""

    @property
    def rule_id(self) -> str:
        return "spoof_frozen_position"

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

        # Check frozen position first (more severe indicator)
        result = self._check_frozen(sorted_pos)
        if result:
            return result

        # Check box pattern
        result = self._check_box_pattern(sorted_pos)
        if result:
            return result

        return RuleResult(fired=False, rule_id=self.rule_id)

    # ------------------------------------------------------------------
    # Detection methods
    # ------------------------------------------------------------------

    def _check_frozen(
        self, positions: Sequence[dict[str, Any]]
    ) -> Optional[RuleResult]:
        """Detect identical lat/lon/COG/SOG for > 2 hours, not anchored."""
        if len(positions) < 2:
            return None

        # Check nav_status — legitimate if anchored/moored
        latest = positions[-1]
        nav_status = latest.get("nav_status") or latest.get("navigational_status")
        if nav_status in _STATIONARY_NAV_STATUSES:
            return None

        # Find runs of identical positions
        run_start_idx = 0
        for i in range(1, len(positions)):
            prev = positions[i - 1]
            curr = positions[i]

            lat_same = (
                prev.get("lat") is not None
                and curr.get("lat") is not None
                and abs(prev["lat"] - curr["lat"]) <= _POSITION_TOLERANCE_DEG
            )
            lon_same = (
                prev.get("lon") is not None
                and curr.get("lon") is not None
                and abs(prev["lon"] - curr["lon"]) <= _POSITION_TOLERANCE_DEG
            )
            cog_same = True
            if prev.get("cog") is not None and curr.get("cog") is not None:
                cog_same = abs(prev["cog"] - curr["cog"]) <= _SPEED_TOLERANCE_KN

            sog_same = True
            if prev.get("sog") is not None and curr.get("sog") is not None:
                sog_same = abs(prev["sog"] - curr["sog"]) <= _SPEED_TOLERANCE_KN

            if not (lat_same and lon_same and cog_same and sog_same):
                run_start_idx = i
                continue

            # Check duration of current run
            ts_start = _parse_ts(positions[run_start_idx].get("timestamp"))
            ts_curr = _parse_ts(curr.get("timestamp"))
            if ts_start is None or ts_curr is None:
                continue

            duration_hours = (ts_curr - ts_start).total_seconds() / 3600.0
            if duration_hours >= _FROZEN_MIN_HOURS:
                return RuleResult(
                    fired=True,
                    rule_id=self.rule_id,
                    severity="high",
                    points=40.0,
                    details={
                        "reason": "frozen_position",
                        "duration_hours": round(duration_hours, 2),
                        "position_count": i - run_start_idx + 1,
                        "lat": curr.get("lat"),
                        "lon": curr.get("lon"),
                        "sog": curr.get("sog"),
                        "cog": curr.get("cog"),
                    },
                    source="realtime",
                )

        return None

    def _check_box_pattern(
        self, positions: Sequence[dict[str, Any]]
    ) -> Optional[RuleResult]:
        """Detect positions oscillating between 2-4 coordinate pairs for > 1 hour."""
        if len(positions) < 4:
            return None

        # Check nav_status
        latest = positions[-1]
        nav_status = latest.get("nav_status") or latest.get("navigational_status")
        if nav_status in _STATIONARY_NAV_STATUSES:
            return None

        # Check time span
        ts_first = _parse_ts(positions[0].get("timestamp"))
        ts_last = _parse_ts(positions[-1].get("timestamp"))
        if ts_first is None or ts_last is None:
            return None

        duration_hours = (ts_last - ts_first).total_seconds() / 3600.0
        if duration_hours < _BOX_MIN_HOURS:
            return None

        # Round positions and count distinct coordinate pairs
        rounded_positions = []
        for pos in positions:
            lat = pos.get("lat")
            lon = pos.get("lon")
            if lat is None or lon is None:
                continue
            rounded_positions.append(_round_position(lat, lon))

        if len(rounded_positions) < 4:
            return None

        distinct = set(rounded_positions)
        n_distinct = len(distinct)

        # Box pattern: 2-4 distinct pairs, with each appearing multiple times
        if 2 <= n_distinct <= _BOX_MAX_DISTINCT_PAIRS:
            counts = Counter(rounded_positions)
            # Each pair must appear at least twice for it to be oscillating
            if all(c >= 2 for c in counts.values()):
                return RuleResult(
                    fired=True,
                    rule_id=self.rule_id,
                    severity="high",
                    points=40.0,
                    details={
                        "reason": "box_pattern",
                        "duration_hours": round(duration_hours, 2),
                        "distinct_positions": n_distinct,
                        "position_count": len(rounded_positions),
                        "pairs": [
                            {"lat": lat, "lon": lon, "count": count}
                            for (lat, lon), count in counts.most_common()
                        ],
                    },
                    source="realtime",
                )

        return None
