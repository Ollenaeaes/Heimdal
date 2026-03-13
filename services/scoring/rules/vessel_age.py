"""Vessel Age rule.

Flags older tankers — vessels with ship_type 80-89 (tankers) that are
past their expected operational lifespan.  Aged tankers are common in
shadow fleets because they are cheap to acquire.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule

_CURRENT_YEAR = 2026

# Ship type range for tankers (AIS ship type codes 80-89)
_TANKER_TYPE_MIN = 80
_TANKER_TYPE_MAX = 89

# Three-tier progressive scoring thresholds: (min_age, severity, points)
_THRESHOLDS = [
    (25, "high", 25.0),      # 25+ years
    (20, "moderate", 15.0),   # 20-24 years
    (15, "low", 5.0),         # 15-19 years
]


class VesselAgeRule(ScoringRule):
    """Fire when a tanker exceeds an age threshold."""

    @property
    def rule_id(self) -> str:
        return "vessel_age"

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
        if not profile:
            return None

        ship_type = profile.get("ship_type")
        build_year = profile.get("build_year")

        if ship_type is None or build_year is None:
            return None

        # Only tankers (ship_type 80-89)
        if not (_TANKER_TYPE_MIN <= ship_type <= _TANKER_TYPE_MAX):
            return RuleResult(fired=False, rule_id=self.rule_id)

        age = _CURRENT_YEAR - build_year

        for min_age, severity, points in _THRESHOLDS:
            if age >= min_age:
                return RuleResult(
                    fired=True,
                    rule_id=self.rule_id,
                    severity=severity,
                    points=points,
                    details={
                        "build_year": build_year,
                        "age_years": age,
                        "ship_type": ship_type,
                    },
                    source="realtime",
                )

        return RuleResult(fired=False, rule_id=self.rule_id)
