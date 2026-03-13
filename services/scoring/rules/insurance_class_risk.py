"""Insurance and Classification Risk rule.

Scores vessels based on P&I insurance coverage and classification society
status.  Vessels without proper insurance or classification represent
higher risk — common indicators of shadow fleet operations.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule

# AIS ship type codes for tankers
_TANKER_TYPE_MIN = 80
_TANKER_TYPE_MAX = 89

IACS_MEMBERS: frozenset[str] = frozenset({
    "ABS", "BV", "CCS", "CRS", "DNV", "IRS", "KR", "LR", "NK", "PRS",
    "RINA", "RS",
})

IACS_FULL_NAMES: dict[str, str] = {
    "AMERICAN BUREAU OF SHIPPING": "ABS",
    "BUREAU VERITAS": "BV",
    "CHINA CLASSIFICATION SOCIETY": "CCS",
    "CROATIAN REGISTER": "CRS",
    "DET NORSKE VERITAS": "DNV",
    "DNV GL": "DNV",
    "INDIAN REGISTER": "IRS",
    "KOREAN REGISTER": "KR",
    "LLOYD'S REGISTER": "LR",
    "LLOYDS REGISTER": "LR",
    "NIPPON KAIJI KYOKAI": "NK",
    "CLASSNK": "NK",
    "POLISH REGISTER": "PRS",
    "RINA": "RINA",
    "RUSSIAN MARITIME REGISTER": "RS",
}


def _is_iacs(class_society: str | None) -> tuple[bool, bool]:
    """Return (is_iacs, is_russian_register)."""
    if not class_society:
        return False, False
    upper = class_society.upper().strip()
    # Direct code match
    if upper in IACS_MEMBERS:
        return True, upper == "RS"
    # Full name / substring match
    for name, code in IACS_FULL_NAMES.items():
        if name in upper:
            return True, code == "RS"
    return False, False


def _is_tanker(ship_type: Any) -> bool:
    """Return True if ship_type falls in the tanker range (80-89)."""
    if ship_type is None:
        return False
    try:
        st = int(ship_type)
    except (ValueError, TypeError):
        return False
    return _TANKER_TYPE_MIN <= st <= _TANKER_TYPE_MAX


def _has_ig_pi(profile: dict[str, Any]) -> bool:
    """Check if vessel has International Group P&I coverage."""
    # Check pi_details first (most reliable)
    pi_details = profile.get("pi_details")
    if isinstance(pi_details, dict):
        if pi_details.get("is_ig_member"):
            return True
    # Check pi_tier
    pi_tier = profile.get("pi_tier")
    if pi_tier and str(pi_tier).upper() in ("IG", "TIER_1", "TIER1"):
        return True
    return False


class InsuranceClassRiskRule(ScoringRule):
    """Fire when a vessel has insurance or classification risk indicators."""

    @property
    def rule_id(self) -> str:
        return "insurance_class_risk"

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

        findings: list[dict[str, Any]] = []
        max_severity = "low"
        total_points = 0.0

        ship_type = profile.get("ship_type")
        is_tanker = _is_tanker(ship_type)
        class_society = profile.get("class_society")
        is_iacs, is_russian = _is_iacs(class_society)

        # --- 1. No classification at all (critical, 25 pts) ---
        if not class_society:
            findings.append({
                "check": "no_classification",
                "severity": "critical",
                "points": 25,
                "reason": "Vessel has no classification society",
            })
            total_points += 25
            max_severity = "critical"

        # --- 2. Non-IACS classification (moderate, 8 pts) ---
        elif not is_iacs:
            findings.append({
                "check": "non_iacs_classification",
                "severity": "moderate",
                "points": 8,
                "class_society": class_society,
                "reason": f"Non-IACS classification society: {class_society}",
            })
            total_points += 8
            max_severity = _escalate(max_severity, "moderate")

        # --- 3. Russian Maritime Register (high, 15 pts) ---
        elif is_russian:
            findings.append({
                "check": "russian_maritime_register",
                "severity": "high",
                "points": 15,
                "class_society": class_society,
                "reason": "Classified by Russian Maritime Register",
            })
            total_points += 15
            max_severity = _escalate(max_severity, "high")

        # --- 4. No IG P&I coverage ---
        if not _has_ig_pi(profile):
            if is_tanker:
                # Tanker without IG P&I → high (15 pts)
                findings.append({
                    "check": "no_ig_pi_tanker",
                    "severity": "high",
                    "points": 15,
                    "ship_type": ship_type,
                    "reason": "Tanker without International Group P&I coverage",
                })
                total_points += 15
                max_severity = _escalate(max_severity, "high")
            else:
                # Non-tanker without IG P&I → moderate (8 pts)
                insurer = profile.get("insurer")
                if insurer is None and not (
                    isinstance(profile.get("pi_details"), dict)
                    and profile["pi_details"].get("provider")
                ):
                    # Only flag if there's truly no insurance info
                    findings.append({
                        "check": "no_ig_pi_non_tanker",
                        "severity": "moderate",
                        "points": 8,
                        "ship_type": ship_type,
                        "reason": "Non-tanker without IG P&I coverage or known insurer",
                    })
                    total_points += 8
                    max_severity = _escalate(max_severity, "moderate")

        # --- 5. Recent class change (< 12 months) → moderate (8 pts) ---
        # Check for class change info in profile or manual enrichment
        prev_class = profile.get("previous_class_society")
        class_change_date = profile.get("class_change_date")
        if prev_class and class_change_date:
            findings.append({
                "check": "recent_class_change",
                "severity": "moderate",
                "points": 8,
                "previous_class": prev_class,
                "current_class": class_society,
                "change_date": str(class_change_date),
                "reason": f"Recent class change from {prev_class} to {class_society}",
            })
            total_points += 8
            max_severity = _escalate(max_severity, "moderate")

        # --- No findings → rule does not fire ---
        if not findings:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # --- 6. Combined factors escalation ---
        if len(findings) >= 2:
            max_severity = _escalate(max_severity, "high")
            if any(f["severity"] == "critical" for f in findings):
                max_severity = "critical"

        return RuleResult(
            fired=True,
            rule_id=self.rule_id,
            severity=max_severity,
            points=total_points,
            details={
                "findings": findings,
                "finding_count": len(findings),
                "is_tanker": is_tanker,
                "class_society": class_society,
            },
            source="realtime",
        )


_SEVERITY_ORDER = {"low": 0, "moderate": 1, "high": 2, "critical": 3}


def _escalate(current: str, candidate: str) -> str:
    """Return the higher severity."""
    if _SEVERITY_ORDER.get(candidate, 0) > _SEVERITY_ORDER.get(current, 0):
        return candidate
    return current
