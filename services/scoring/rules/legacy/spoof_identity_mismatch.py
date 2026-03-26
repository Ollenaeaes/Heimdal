"""Spoofing detection: MMSI-IMO cross-reference mismatch.

Detects identity spoofing by cross-referencing AIS-reported identity
against IMO registry data (from GFW vessel profile):

1. **Dimension mismatch** — length or beam > 20% different from registry.
2. **Zombie vessel** — IMO belongs to a vessel marked as scrapped/broken up.
3. **Flag-MID mismatch** — MMSI's Maritime Identification Digits don't
   match the registered flag state.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from shared.constants import MID_TO_FLAG, normalize_flag as _normalize_flag
from shared.models.anomaly import RuleResult

from .base import ScoringRule

_DIMENSION_MISMATCH_PCT = 0.20  # 20%


class SpoofIdentityMismatchRule(ScoringRule):
    """Fire on MMSI-IMO cross-reference mismatches indicating spoofing."""

    @property
    def rule_id(self) -> str:
        return "spoof_identity_mismatch"

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

        # Need GFW data for cross-referencing
        gfw_data = profile.get("gfw_data") or profile.get("gfw_vessel_info")
        if not gfw_data:
            return None

        # Collect all findings, return highest severity
        findings: list[RuleResult] = []

        # 1. Zombie vessel check
        zombie = self._check_zombie(profile, gfw_data)
        if zombie:
            findings.append(zombie)

        # 2. Dimension mismatch
        dim = self._check_dimensions(profile, gfw_data)
        if dim:
            findings.append(dim)

        # 3. Flag-MID mismatch
        flag = self._check_flag_mid_mismatch(mmsi, profile, gfw_data)
        if flag:
            findings.append(flag)

        if not findings:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Return highest severity finding
        severity_order = {"critical": 0, "high": 1, "moderate": 2, "low": 3}
        findings.sort(key=lambda r: severity_order.get(r.severity or "low", 99))
        return findings[0]

    # ------------------------------------------------------------------

    def _check_zombie(
        self, profile: dict[str, Any], gfw_data: dict[str, Any]
    ) -> Optional[RuleResult]:
        """Check if the IMO belongs to a scrapped/broken up vessel."""
        vessel_status = gfw_data.get("vessel_status") or gfw_data.get("status")
        if not vessel_status:
            return None

        status_lower = str(vessel_status).lower()
        zombie_indicators = ("scrapped", "broken up", "hulled", "total loss", "sunk")

        if any(ind in status_lower for ind in zombie_indicators):
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="critical",
                points=100.0,
                details={
                    "reason": "zombie_vessel",
                    "vessel_status": vessel_status,
                    "imo": profile.get("imo"),
                },
                source="realtime",
            )
        return None

    def _check_dimensions(
        self, profile: dict[str, Any], gfw_data: dict[str, Any]
    ) -> Optional[RuleResult]:
        """Check for significant dimension mismatch between AIS and registry."""
        mismatches: list[dict[str, Any]] = []

        # GFW reference dimensions
        ref_length = gfw_data.get("length") or gfw_data.get("lengthOverall")
        ref_beam = gfw_data.get("beam") or gfw_data.get("width")

        ais_length = profile.get("length")
        ais_beam = profile.get("width") or profile.get("beam")

        if ref_length and ais_length and ref_length > 0:
            pct_diff = abs(ais_length - ref_length) / ref_length
            if pct_diff > _DIMENSION_MISMATCH_PCT:
                mismatches.append({
                    "field": "length",
                    "registry_value": ref_length,
                    "ais_value": ais_length,
                    "pct_diff": round(pct_diff * 100, 1),
                })

        if ref_beam and ais_beam and ref_beam > 0:
            pct_diff = abs(ais_beam - ref_beam) / ref_beam
            if pct_diff > _DIMENSION_MISMATCH_PCT:
                mismatches.append({
                    "field": "beam",
                    "registry_value": ref_beam,
                    "ais_value": ais_beam,
                    "pct_diff": round(pct_diff * 100, 1),
                })

        if mismatches:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="high",
                points=40.0,
                details={
                    "reason": "dimension_mismatch",
                    "mismatches": mismatches,
                },
                source="realtime",
            )
        return None

    def _check_flag_mid_mismatch(
        self,
        mmsi: int,
        profile: dict[str, Any],
        gfw_data: dict[str, Any],
    ) -> Optional[RuleResult]:
        """Check if MMSI's MID doesn't match the registered flag."""
        mid = int(str(mmsi)[:3])
        mmsi_flag = MID_TO_FLAG.get(mid)

        registered_flag = (
            gfw_data.get("flag") or
            gfw_data.get("flag_country") or
            profile.get("flag_country")
        )

        if not mmsi_flag or not registered_flag:
            return None

        norm_mmsi = _normalize_flag(mmsi_flag)
        norm_registered = _normalize_flag(registered_flag)

        if norm_mmsi != norm_registered:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="high",
                points=40.0,
                details={
                    "reason": "flag_mid_mismatch",
                    "mmsi_derived_flag": norm_mmsi or mmsi_flag,
                    "registered_flag": norm_registered or registered_flag,
                    "mid": mid,
                },
                source="realtime",
            )
        return None
