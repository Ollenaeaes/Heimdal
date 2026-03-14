"""Spoofing detection: physically impossible speed.

Fires when the implied speed between consecutive AIS positions exceeds
a ship-type-specific maximum (with a 1.5x safety margin).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .ais_spoofing import haversine_nm
from .base import ScoringRule

# ---------------------------------------------------------------------------
# Ship-type-specific max speeds (knots) — threshold = base * 1.5
# ---------------------------------------------------------------------------
# AIS ship_type ranges:
#   70-79: Cargo (includes container, bulk, general cargo)
#   80-89: Tanker

_TANKER_TYPES = range(80, 90)
_CARGO_TYPES = range(70, 80)

# Base max speeds (knots)
_SPEED_TANKER = 18.0
_SPEED_BULK_CARRIER = 16.0
_SPEED_CONTAINER = 25.0
_SPEED_GENERAL_CARGO = 16.0
_SPEED_TUG = 14.0
_SPEED_DEFAULT = 30.0

# Threshold multiplier
_THRESHOLD_FACTOR = 1.5

# Ship type text patterns for distinguishing cargo sub-types
_CONTAINER_KEYWORDS = frozenset({
    "container", "containership", "container ship",
})
_TUG_KEYWORDS = frozenset({
    "tug", "tugboat", "towing",
})
_BULK_KEYWORDS = frozenset({
    "bulk", "bulk carrier", "bulker",
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


def _get_speed_threshold(
    ship_type: int | None,
    ship_type_text: str | None,
) -> float:
    """Return the impossible-speed threshold for a vessel type."""
    text_lower = (ship_type_text or "").lower().strip()

    # Check text-based classification first (more specific)
    if any(kw in text_lower for kw in _TUG_KEYWORDS):
        return _SPEED_TUG * _THRESHOLD_FACTOR
    if any(kw in text_lower for kw in _CONTAINER_KEYWORDS):
        return _SPEED_CONTAINER * _THRESHOLD_FACTOR
    if any(kw in text_lower for kw in _BULK_KEYWORDS):
        return _SPEED_BULK_CARRIER * _THRESHOLD_FACTOR

    # Fall back to AIS ship_type numeric code
    if ship_type is not None:
        if ship_type in _TANKER_TYPES:
            return _SPEED_TANKER * _THRESHOLD_FACTOR
        if ship_type in _CARGO_TYPES:
            return _SPEED_GENERAL_CARGO * _THRESHOLD_FACTOR

    return _SPEED_DEFAULT * _THRESHOLD_FACTOR


class SpoofImpossibleSpeedRule(ScoringRule):
    """Fire when implied speed between positions exceeds physical limits."""

    @property
    def rule_id(self) -> str:
        return "spoof_impossible_speed"

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

        ship_type = (profile or {}).get("ship_type")
        ship_type_text = (profile or {}).get("ship_type_text")
        threshold = _get_speed_threshold(ship_type, ship_type_text)

        sorted_pos = sorted(recent_positions, key=lambda p: p.get("timestamp", ""))

        violations: list[dict[str, Any]] = []

        for i in range(1, len(sorted_pos)):
            prev = sorted_pos[i - 1]
            curr = sorted_pos[i]

            ts_prev = _parse_ts(prev.get("timestamp"))
            ts_curr = _parse_ts(curr.get("timestamp"))
            if ts_prev is None or ts_curr is None:
                continue

            delta_seconds = (ts_curr - ts_prev).total_seconds()
            if delta_seconds <= 0:
                continue

            lat1, lon1 = prev.get("lat"), prev.get("lon")
            lat2, lon2 = curr.get("lat"), curr.get("lon")
            if None in (lat1, lon1, lat2, lon2):
                continue

            distance_nm = haversine_nm(lat1, lon1, lat2, lon2)
            delta_hours = delta_seconds / 3600.0
            implied_speed = distance_nm / delta_hours

            if implied_speed > threshold:
                violations.append({
                    "implied_speed_knots": round(implied_speed, 2),
                    "distance_nm": round(distance_nm, 2),
                    "delta_seconds": round(delta_seconds, 1),
                    "timestamp": str(ts_curr),
                })

        if not violations:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # 2+ violations in 24h → critical
        # Check if violations span within 24 hours
        if len(violations) >= 2:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="critical",
                points=100.0,
                details={
                    "reason": "repeated_impossible_speed",
                    "violation_count": len(violations),
                    "threshold_knots": threshold,
                    "violations": violations[:5],  # cap detail size
                },
                source="realtime",
            )

        # Single violation → high
        return RuleResult(
            fired=True,
            rule_id=self.rule_id,
            severity="high",
            points=40.0,
            details={
                "reason": "impossible_speed",
                "threshold_knots": threshold,
                "violations": violations,
            },
            source="realtime",
        )
