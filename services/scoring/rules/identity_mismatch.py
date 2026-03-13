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

# ISO 3166-1 alpha-3 → alpha-2 mapping for common maritime flags.
# AIS sometimes reports alpha-3 codes while MMSI MID maps to alpha-2.
_ALPHA3_TO_ALPHA2: dict[str, str] = {
    "CYP": "CY", "GBR": "GB", "GRC": "GR", "MLT": "MT", "PAN": "PA",
    "LBR": "LR", "MHL": "MH", "NOR": "NO", "SWE": "SE", "DNK": "DK",
    "DEU": "DE", "NLD": "NL", "FRA": "FR", "ESP": "ES", "ITA": "IT",
    "PRT": "PT", "FIN": "FI", "IRL": "IE", "BEL": "BE", "HRV": "HR",
    "ROU": "RO", "BGR": "BG", "POL": "PL", "EST": "EE", "LVA": "LV",
    "LTU": "LT", "SVN": "SI", "TUR": "TR", "RUS": "RU", "UKR": "UA",
    "USA": "US", "CAN": "CA", "BHS": "BS", "BMU": "BM", "BRB": "BB",
    "BLZ": "BZ", "CHN": "CN", "TWN": "TW", "JPN": "JP", "KOR": "KR",
    "SGP": "SG", "HKG": "HK", "IND": "IN", "IDN": "ID", "MYS": "MY",
    "PHL": "PH", "THA": "TH", "VNM": "VN", "AUS": "AU", "NZL": "NZ",
    "BRA": "BR", "ARG": "AR", "CHL": "CL", "COL": "CO", "MEX": "MX",
    "ARE": "AE", "SAU": "SA", "IRN": "IR", "ISR": "IL", "EGY": "EG",
    "ZAF": "ZA", "NGA": "NG", "KEN": "KE", "TZA": "TZ", "GHA": "GH",
    "COM": "KM", "CMR": "CM", "GAB": "GA", "TGO": "TG", "SEN": "SN",
    "ATG": "AG", "VCT": "VC", "KNA": "KN", "DMA": "DM", "GRD": "GD",
    "TTO": "TT", "CRI": "CR", "CUB": "CU", "DOM": "DO", "GTM": "GT",
    "HND": "HN", "NIC": "NI", "SLV": "SV", "JAM": "JM", "GIB": "GI",
    "ISL": "IS", "FRO": "FO", "MCO": "MC", "LUX": "LU", "AND": "AD",
    "MNE": "ME", "ALB": "AL", "GEO": "GE", "PLW": "PW", "TUV": "TV",
    "VUT": "VU", "TON": "TO", "FJI": "FJ", "WSM": "WS", "KIR": "KI",
}


def _normalize_flag(flag: str) -> str:
    """Normalize a flag code to ISO alpha-2 uppercase."""
    flag = flag.strip().upper()
    return _ALPHA3_TO_ALPHA2.get(flag, flag)


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

        # Normalize both to alpha-2 before comparing (e.g. CYP → CY)
        if _normalize_flag(mmsi_flag) != _normalize_flag(reported_flag):
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
