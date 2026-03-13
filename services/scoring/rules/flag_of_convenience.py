"""Flag of Convenience rule.

Flags vessels registered under known shadow-fleet flag states. These are
flags with minimal oversight that are disproportionately used by vessels
engaged in sanctions evasion and deceptive shipping practices.

Uses the SHADOW_FLEET_FLAGS set from shared.constants which includes
Comoros, Cameroon, Palau, Gabon, Tanzania, Togo, etc.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from shared.constants import FRAUDULENT_REGISTRY_FLAGS, MID_TO_FLAG, SHADOW_FLEET_FLAGS
from shared.models.anomaly import RuleResult

from .base import ScoringRule


class FlagOfConvenienceRule(ScoringRule):
    """Fire when a vessel flies a flag associated with shadow fleet activity."""

    @property
    def rule_id(self) -> str:
        return "flag_of_convenience"

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

        # Determine flag from profile or derive from MMSI MID
        flag = (profile.get("flag_country") or "").strip().upper()
        if not flag:
            mid = mmsi // 1000000
            flag = MID_TO_FLAG.get(mid, "")

        if not flag:
            return None

        # Fraudulent registries = high risk (20 points)
        if flag in FRAUDULENT_REGISTRY_FLAGS:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="high",
                points=20.0,
                details={
                    "flag": flag,
                    "mmsi_mid": mmsi // 1000000,
                    "risk_level": "high",
                    "reason": "fraudulent_registry",
                },
                source="realtime",
            )

        # Standard FoC = low risk (5 points)
        if flag in SHADOW_FLEET_FLAGS:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="low",
                points=5.0,
                details={
                    "flag": flag,
                    "mmsi_mid": mmsi // 1000000,
                    "risk_level": "low",
                    "reason": "shadow_fleet_associated_flag",
                },
                source="realtime",
            )

        return RuleResult(fired=False, rule_id=self.rule_id)
