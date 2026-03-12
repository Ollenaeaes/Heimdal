"""Identity Mismatch rule.

Detects discrepancies between a vessel's IMO-registered physical
dimensions and its AIS-reported values, as well as MMSI-derived flag
vs self-reported flag mismatches.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from shared.constants import MID_TO_FLAG
from shared.models.anomaly import RuleResult

from .base import ScoringRule

_DIMENSION_MISMATCH_PCT = 0.20  # 20 %


class IdentityMismatchRule(ScoringRule):
    """Fire when AIS identity fields contradict registry data."""

    @property
    def rule_id(self) -> str:
        return "identity_mismatch"

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

        # 1. Dimension mismatch check
        dim_result = self._check_dimensions(profile)
        if dim_result:
            return dim_result

        # 2. Flag mismatch check
        flag_result = self._check_flag_mismatch(mmsi, profile)
        if flag_result:
            return flag_result

        return RuleResult(fired=False, rule_id=self.rule_id)

    # ------------------------------------------------------------------

    def _check_dimensions(
        self, profile: dict[str, Any]
    ) -> Optional[RuleResult]:
        """Compare IMO-based reference dimensions against AIS-reported."""
        # We need both reference and reported dimensions
        imo_length = profile.get("imo_length") or profile.get("reference_length")
        imo_width = profile.get("imo_width") or profile.get("reference_width")
        ais_length = profile.get("length")
        ais_width = profile.get("width")

        mismatches: list[dict[str, Any]] = []

        if imo_length and ais_length and imo_length > 0:
            pct_diff = abs(ais_length - imo_length) / imo_length
            if pct_diff > _DIMENSION_MISMATCH_PCT:
                mismatches.append({
                    "field": "length",
                    "imo_value": imo_length,
                    "ais_value": ais_length,
                    "pct_diff": round(pct_diff * 100, 1),
                })

        if imo_width and ais_width and imo_width > 0:
            pct_diff = abs(ais_width - imo_width) / imo_width
            if pct_diff > _DIMENSION_MISMATCH_PCT:
                mismatches.append({
                    "field": "width",
                    "imo_value": imo_width,
                    "ais_value": ais_width,
                    "pct_diff": round(pct_diff * 100, 1),
                })

        if mismatches:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="critical",
                points=100.0,
                details={
                    "reason": "dimension_mismatch",
                    "mismatches": mismatches,
                },
                source="realtime",
            )
        return None

    def _check_flag_mismatch(
        self, mmsi: int, profile: dict[str, Any]
    ) -> Optional[RuleResult]:
        """Compare MMSI-derived flag against the self-reported flag_country."""
        mid = int(str(mmsi)[:3])
        mmsi_flag = MID_TO_FLAG.get(mid)
        reported_flag = profile.get("flag_country")

        if not mmsi_flag or not reported_flag:
            return None

        if mmsi_flag != reported_flag:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="high",
                points=40.0,
                details={
                    "reason": "flag_mismatch",
                    "mmsi_derived_flag": mmsi_flag,
                    "reported_flag": reported_flag,
                    "mid": mid,
                },
                source="realtime",
            )
        return None
