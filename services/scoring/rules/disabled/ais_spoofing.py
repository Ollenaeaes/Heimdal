"""AIS Position Spoofing detection rule.

Detects four types of AIS position spoofing:

1. **Position jump** — consecutive positions with impossible implied speed
   (> 500 nm in < 1 hour, i.e. > 50 knots).
2. **Circle spoofing** — positions forming a near-perfect circle around a
   centroid while claiming to be underway.
3. **Anchor spoofing** — vessel hasn't moved but nav_status says "underway".
4. **Slow-roll spoofing** — unrealistically slow movement with no position
   variance, not anchored/moored.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_POSITION_JUMP_NM = 500.0
_POSITION_JUMP_MAX_HOURS = 1.0

_CIRCLE_MIN_POSITIONS = 6
_CIRCLE_MAX_VARIANCE_DEG = 0.01
_CIRCLE_MIN_MEAN_RADIUS_DEG = 0.005  # must have meaningful spread from centroid
_CIRCLE_MIN_HOURS = 24.0

_ANCHOR_SPOOF_MIN_HOURS = 48.0
_ANCHOR_SPOOF_MAX_MOVEMENT_DEG = 0.001

_SLOW_ROLL_MIN_HOURS = 12.0
_SLOW_ROLL_MAX_SOG = 0.5
_SLOW_ROLL_MAX_HEADING_VARIANCE = 1.0  # degrees

# AIS nav status codes that indicate the vessel is stationary
_STATIONARY_NAV_STATUSES = frozenset({
    "Moored", "At anchor", "Aground", "Not under command",
    1, 5, 6,  # at anchor, moored, aground
})

# AIS nav status codes that mean "underway"
_UNDERWAY_NAV_STATUSES = frozenset({
    "Under way using engine", "Under way sailing",
    0, 8,  # under way using engine, under way sailing
})


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------

def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles."""
    R_NM = 3440.065  # Earth radius in NM
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R_NM * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_ts(ts: Any) -> Optional[datetime]:
    """Parse a timestamp value into a timezone-aware datetime."""
    if ts is None:
        return None
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    return None


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------

class AisSpoofingRule(ScoringRule):
    """Detect AIS position spoofing patterns."""

    @property
    def rule_id(self) -> str:
        return "ais_spoofing"

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

        # 1. Position jump (most severe indicator)
        result = self._check_position_jump(sorted_pos)
        if result:
            return result

        # 2. Anchor spoofing (check before circle — stationary positions
        #    could also satisfy the circle variance check)
        result = self._check_anchor_spoofing(sorted_pos)
        if result:
            return result

        # 3. Circle spoofing
        result = self._check_circle_spoofing(sorted_pos)
        if result:
            return result

        # 4. Slow-roll spoofing
        result = self._check_slow_roll(sorted_pos)
        if result:
            return result

        return RuleResult(fired=False, rule_id=self.rule_id)

    async def check_event_ended(
        self,
        mmsi: int,
        profile: dict[str, Any] | None,
        recent_positions: Sequence[dict[str, Any]],
        active_anomaly: dict[str, Any],
    ) -> bool:
        """End when none of the spoofing checks trigger anymore."""
        if len(recent_positions) < 2:
            return False
        result = await self.evaluate(mmsi, profile, recent_positions, [], [])
        return result is None or not result.fired

    # ------------------------------------------------------------------
    # Detection methods
    # ------------------------------------------------------------------

    def _check_position_jump(
        self, positions: list[dict[str, Any]]
    ) -> Optional[RuleResult]:
        """Detect impossible position jumps (> 500nm in < 1 hour)."""
        for i in range(1, len(positions)):
            prev = positions[i - 1]
            curr = positions[i]

            ts_prev = _parse_ts(prev.get("timestamp"))
            ts_curr = _parse_ts(curr.get("timestamp"))
            if ts_prev is None or ts_curr is None:
                continue

            delta_hours = (ts_curr - ts_prev).total_seconds() / 3600.0
            if delta_hours <= 0 or delta_hours > _POSITION_JUMP_MAX_HOURS:
                continue

            lat1 = prev.get("lat")
            lon1 = prev.get("lon")
            lat2 = curr.get("lat")
            lon2 = curr.get("lon")
            if None in (lat1, lon1, lat2, lon2):
                continue

            distance = haversine_nm(lat1, lon1, lat2, lon2)
            if distance > _POSITION_JUMP_NM:
                implied_speed = distance / delta_hours
                return RuleResult(
                    fired=True,
                    rule_id=self.rule_id,
                    severity="critical",
                    points=30.0,
                    details={
                        "reason": "position_jump",
                        "distance_nm": round(distance, 2),
                        "delta_hours": round(delta_hours, 4),
                        "implied_speed_knots": round(implied_speed, 2),
                    },
                    source="realtime",
                )
        return None

    def _check_circle_spoofing(
        self, positions: list[dict[str, Any]]
    ) -> Optional[RuleResult]:
        """Detect positions forming a near-perfect circle while claiming underway."""
        if len(positions) < _CIRCLE_MIN_POSITIONS:
            return None

        # Check time span
        ts_first = _parse_ts(positions[0].get("timestamp"))
        ts_last = _parse_ts(positions[-1].get("timestamp"))
        if ts_first is None or ts_last is None:
            return None

        span_hours = (ts_last - ts_first).total_seconds() / 3600.0
        if span_hours < _CIRCLE_MIN_HOURS:
            return None

        # Must be claiming underway (or at least not stationary)
        latest = positions[-1]
        nav_status = latest.get("nav_status") or latest.get("navigational_status")
        if nav_status in _STATIONARY_NAV_STATUSES:
            return None

        # Calculate centroid
        lats = [p["lat"] for p in positions if p.get("lat") is not None]
        lons = [p["lon"] for p in positions if p.get("lon") is not None]
        if len(lats) < _CIRCLE_MIN_POSITIONS:
            return None

        centroid_lat = sum(lats) / len(lats)
        centroid_lon = sum(lons) / len(lons)

        # Calculate variance from centroid (in degrees)
        distances = [
            math.sqrt((lat - centroid_lat) ** 2 + (lon - centroid_lon) ** 2)
            for lat, lon in zip(lats, lons)
        ]
        mean_dist = sum(distances) / len(distances)
        if mean_dist < _CIRCLE_MIN_MEAN_RADIUS_DEG:
            # Too close together — this is a stationary cluster, not a circle
            return None

        variance = sum((d - mean_dist) ** 2 for d in distances) / len(distances)

        if variance < _CIRCLE_MAX_VARIANCE_DEG:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="critical",
                points=30.0,
                details={
                    "reason": "circle_spoofing",
                    "position_count": len(positions),
                    "duration_hours": round(span_hours, 2),
                    "centroid_lat": round(centroid_lat, 6),
                    "centroid_lon": round(centroid_lon, 6),
                    "variance_deg": round(variance, 8),
                },
                source="realtime",
            )
        return None

    def _check_anchor_spoofing(
        self, positions: list[dict[str, Any]]
    ) -> Optional[RuleResult]:
        """Detect stationary vessel claiming to be underway for > 48 hours."""
        if len(positions) < 2:
            return None

        ts_first = _parse_ts(positions[0].get("timestamp"))
        ts_last = _parse_ts(positions[-1].get("timestamp"))
        if ts_first is None or ts_last is None:
            return None

        span_hours = (ts_last - ts_first).total_seconds() / 3600.0
        if span_hours < _ANCHOR_SPOOF_MIN_HOURS:
            return None

        # All positions must be within a tiny box
        lats = [p["lat"] for p in positions if p.get("lat") is not None]
        lons = [p["lon"] for p in positions if p.get("lon") is not None]
        if not lats or not lons:
            return None

        lat_range = max(lats) - min(lats)
        lon_range = max(lons) - min(lons)

        if lat_range > _ANCHOR_SPOOF_MAX_MOVEMENT_DEG or lon_range > _ANCHOR_SPOOF_MAX_MOVEMENT_DEG:
            return None

        # Check that nav_status is NOT stationary (i.e. claiming underway)
        latest = positions[-1]
        nav_status = latest.get("nav_status") or latest.get("navigational_status")
        if nav_status in _STATIONARY_NAV_STATUSES:
            return None

        return RuleResult(
            fired=True,
            rule_id=self.rule_id,
            severity="critical",
            points=30.0,
            details={
                "reason": "anchor_spoofing",
                "duration_hours": round(span_hours, 2),
                "lat_range_deg": round(lat_range, 6),
                "lon_range_deg": round(lon_range, 6),
                "nav_status": nav_status,
            },
            source="realtime",
        )

    def _check_slow_roll(
        self, positions: list[dict[str, Any]]
    ) -> Optional[RuleResult]:
        """Detect unrealistically slow movement with no heading change."""
        if len(positions) < 2:
            return None

        ts_first = _parse_ts(positions[0].get("timestamp"))
        ts_last = _parse_ts(positions[-1].get("timestamp"))
        if ts_first is None or ts_last is None:
            return None

        span_hours = (ts_last - ts_first).total_seconds() / 3600.0
        if span_hours < _SLOW_ROLL_MIN_HOURS:
            return None

        # Latest nav_status must NOT be stationary
        latest = positions[-1]
        nav_status = latest.get("nav_status") or latest.get("navigational_status")
        if nav_status in _STATIONARY_NAV_STATUSES:
            return None

        # All SOGs must be < 0.5 knots
        sogs = [p.get("sog") for p in positions if p.get("sog") is not None]
        if not sogs:
            return None
        if any(s > _SLOW_ROLL_MAX_SOG for s in sogs):
            return None

        # Heading variance must be minimal
        headings = [p.get("heading") for p in positions if p.get("heading") is not None]
        if len(headings) < 2:
            return None

        mean_heading = sum(headings) / len(headings)
        heading_variance = sum((h - mean_heading) ** 2 for h in headings) / len(headings)

        if heading_variance > _SLOW_ROLL_MAX_HEADING_VARIANCE:
            return None

        avg_sog = sum(sogs) / len(sogs)

        return RuleResult(
            fired=True,
            rule_id=self.rule_id,
            severity="critical",
            points=30.0,
            details={
                "reason": "slow_roll_spoofing",
                "duration_hours": round(span_hours, 2),
                "avg_sog_knots": round(avg_sog, 4),
                "heading_variance": round(heading_variance, 4),
            },
            source="realtime",
        )
