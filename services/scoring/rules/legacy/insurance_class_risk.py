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


# International Group of P&I Clubs — 12 member clubs (+ common name variants)
_IG_PI_CLUBS: list[str] = [
    "AMERICAN",       # American Steamship Owners Mutual Protection and Indemnity Association
    "BRITANNIA",      # Britannia P&I Club
    "GARD",           # Assuranceforeningen Gard
    "JAPAN P&I",      # Japan Ship Owners' Mutual Protection & Indemnity Association
    "LONDON P&I",     # London P&I Club
    "NORTH OF ENGLAND", # North of England P&I Association
    "SHIPOWNERS",     # Shipowners' Mutual Protection and Indemnity Association (Luxembourg)
    "SKULD",          # Assuranceforeningen Skuld
    "STANDARD",       # Standard Club
    "STEAMSHIP MUTUAL", # Steamship Mutual Underwriting Association
    "SWEDISH CLUB",   # Sveriges Ångfartygs Assurans Förening (The Swedish Club)
    "UK P&I",         # United Kingdom Mutual Steam Ship Assurance Association
    "WEST OF ENGLAND", # West of England Ship Owners Mutual Insurance Association
]


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
    # Check insurer name against known IG P&I clubs
    insurer = profile.get("insurer")
    if insurer and isinstance(insurer, str):
        upper = insurer.upper()
        for club in _IG_PI_CLUBS:
            if club in upper:
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

        # Has any data source populated insurance/classification info?
        # If not, we can't fairly penalise for missing data.
        # Note: enriched_at alone is NOT sufficient — it's set when any
        # enrichment runs (e.g. sanctions-only). We need evidence that
        # insurance/classification data was actually looked up.
        pi_details = profile.get("pi_details")
        has_pi_details = isinstance(pi_details, dict) and bool(pi_details)
        has_data = bool(
            profile.get("equasis_data")
            or class_society
            or profile.get("insurer")
            or has_pi_details
        )

        # --- 1. No classification at all (critical, 25 pts) ---
        # Only flag if we've actually tried to look it up
        if not class_society and not has_data:
            pass  # No data yet — don't penalise
        elif not class_society:
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

        # --- 4. P&I insurance checks ---
        insurer = profile.get("insurer")
        has_any_pi = bool(
            insurer
            or (isinstance(pi_details, dict) and pi_details.get("provider"))
        )
        has_equasis = bool(profile.get("equasis_data"))

        # 4a. No P&I insurance at all — only flag when Equasis data has been
        #     uploaded (the authoritative source that would list P&I).
        if not has_any_pi and has_equasis:
            pts = 20 if is_tanker else 15
            sev = "critical" if is_tanker else "high"
            findings.append({
                "check": "no_pi_insurance",
                "severity": sev,
                "points": pts,
                "ship_type": ship_type,
                "reason": (
                    "No P&I insurance listed in Equasis data"
                    + (" (tanker)" if is_tanker else "")
                ),
            })
            total_points += pts
            max_severity = _escalate(max_severity, sev)

        # 4b. Has P&I but not IG club — only flag if we have some data source
        elif not _has_ig_pi(profile) and has_data and has_any_pi:
            if is_tanker:
                findings.append({
                    "check": "no_ig_pi_tanker",
                    "severity": "high",
                    "points": 15,
                    "ship_type": ship_type,
                    "insurer": insurer,
                    "reason": f"Tanker without International Group P&I coverage (insurer: {insurer})",
                })
                total_points += 15
                max_severity = _escalate(max_severity, "high")
            else:
                findings.append({
                    "check": "no_ig_pi_non_tanker",
                    "severity": "moderate",
                    "points": 8,
                    "ship_type": ship_type,
                    "insurer": insurer,
                    "reason": f"Non-tanker without IG P&I coverage (insurer: {insurer})",
                })
                total_points += 8
                max_severity = _escalate(max_severity, "moderate")

        # 4c. No IG P&I, no insurer at all, but has other data (non-equasis) —
        #     keep the original softer flag for unenriched-via-equasis vessels
        elif not _has_ig_pi(profile) and has_data and not has_equasis:
            if is_tanker:
                findings.append({
                    "check": "no_ig_pi_tanker",
                    "severity": "high",
                    "points": 15,
                    "ship_type": ship_type,
                    "reason": "Tanker without International Group P&I coverage",
                })
                total_points += 15
                max_severity = _escalate(max_severity, "high")
            elif not has_any_pi:
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

        # --- NEW: Equasis PSC data ---
        equasis_data = profile.get("equasis_data")
        if equasis_data:
            psc_inspections = equasis_data.get("psc_inspections", [])
            if isinstance(psc_inspections, list):
                from datetime import datetime, timezone, timedelta

                three_years_ago = datetime.now(timezone.utc) - timedelta(
                    days=3 * 365
                )

                recent_detentions = 0
                recent_deficiencies = 0
                for insp in psc_inspections:
                    # Parse date
                    date_str = insp.get("date")
                    if not date_str:
                        continue
                    try:
                        parts = date_str.split("/")
                        insp_date = datetime(
                            int(parts[2]),
                            int(parts[1]),
                            int(parts[0]),
                            tzinfo=timezone.utc,
                        )
                    except (ValueError, IndexError):
                        continue
                    if insp_date < three_years_ago:
                        continue

                    # Count detentions
                    if insp.get("detention") is True or str(
                        insp.get("detention", "")
                    ).upper() == "Y":
                        recent_detentions += 1

                    # Count deficiencies
                    deficiency_count = insp.get("deficiencies")
                    if deficiency_count is not None:
                        try:
                            recent_deficiencies += int(deficiency_count)
                        except (ValueError, TypeError):
                            pass

                # Detention findings (capped at 2 detentions = 30 pts)
                if recent_detentions > 0:
                    det_count = min(recent_detentions, 2)
                    det_points = det_count * 15
                    findings.append(
                        {
                            "check": "psc_detention",
                            "severity": "high",
                            "points": det_points,
                            "detention_count": recent_detentions,
                            "reason": f"{recent_detentions} PSC detention(s) in last 3 years",
                        }
                    )
                    total_points += det_points
                    max_severity = _escalate(max_severity, "high")

                # Deficiency findings
                if recent_deficiencies > 25:
                    findings.append(
                        {
                            "check": "psc_high_deficiencies",
                            "severity": "high",
                            "points": 15,
                            "deficiency_count": recent_deficiencies,
                            "reason": f"{recent_deficiencies} PSC deficiencies in last 3 years (>25)",
                        }
                    )
                    total_points += 15
                    max_severity = _escalate(max_severity, "high")
                elif recent_deficiencies > 10:
                    findings.append(
                        {
                            "check": "psc_moderate_deficiencies",
                            "severity": "moderate",
                            "points": 8,
                            "deficiency_count": recent_deficiencies,
                            "reason": f"{recent_deficiencies} PSC deficiencies in last 3 years (>10)",
                        }
                    )
                    total_points += 8
                    max_severity = _escalate(max_severity, "moderate")

            # Classification withdrawn by society
            classification_status = equasis_data.get("classification_status", [])
            if isinstance(classification_status, list):
                for entry in classification_status:
                    status = str(entry.get("status", "")).lower()
                    reason = str(entry.get("reason", "")).lower()
                    society = str(entry.get("society", ""))

                    if "withdrawn" in status and "by society" in reason:
                        findings.append(
                            {
                                "check": "classification_withdrawn_by_society",
                                "severity": "critical",
                                "points": 25,
                                "society": society,
                                "reason": f"Classification withdrawn by {society}: {entry.get('reason', '')}",
                            }
                        )
                        total_points += 25
                        max_severity = "critical"
                        break  # One finding is enough

                # Russian Register + IACS withdrawn combo
                has_russian = any(
                    "russian" in str(e.get("society", "")).lower()
                    for e in classification_status
                    if str(e.get("status", "")).lower() == "delivered"
                )
                has_iacs_withdrawn = any(
                    "withdrawn" in str(e.get("status", "")).lower()
                    and "iacs" in str(e.get("society", "")).lower()
                    for e in classification_status
                )
                if has_russian and has_iacs_withdrawn:
                    # Don't double-count if we already found "withdrawn by society"
                    if not any(
                        f["check"] == "classification_withdrawn_by_society"
                        for f in findings
                    ):
                        findings.append(
                            {
                                "check": "russian_register_iacs_withdrawn",
                                "severity": "high",
                                "points": 20,
                                "reason": "Russian Maritime Register with IACS society classification withdrawn",
                            }
                        )
                        total_points += 20
                        max_severity = _escalate(max_severity, "high")

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


    async def check_event_ended(
        self,
        mmsi: int,
        profile: dict[str, Any] | None,
        recent_positions: Sequence[dict[str, Any]],
        active_anomaly: dict[str, Any],
    ) -> bool:
        """End the anomaly if re-evaluation no longer fires the same checks."""
        result = await self.evaluate(mmsi, profile, recent_positions, [], [])
        if result is None or not result.fired:
            return True
        # Also end if the specific findings have changed (e.g. classification
        # was missing but is now populated)
        old_details = active_anomaly.get("details", {})
        if isinstance(old_details, str):
            import json as _json
            old_details = _json.loads(old_details)
        old_checks = {f["check"] for f in old_details.get("findings", []) if isinstance(f, dict)}
        new_checks = {f["check"] for f in result.details.get("findings", []) if isinstance(f, dict)}
        # If old findings no longer appear, the situation has improved
        if not old_checks.issubset(new_checks):
            return True
        return False


_SEVERITY_ORDER = {"low": 0, "moderate": 1, "high": 2, "critical": 3}


def _escalate(current: str, candidate: str) -> str:
    """Return the higher severity."""
    if _SEVERITY_ORDER.get(candidate, 0) > _SEVERITY_ORDER.get(current, 0):
        return candidate
    return current
