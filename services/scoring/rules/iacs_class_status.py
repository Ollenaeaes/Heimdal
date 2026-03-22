"""IACS Classification Status scoring rule.

Uses the IACS Vessels-in-Class tracker data to score vessels based on their
classification status.  This is the authoritative source for whether a vessel
has valid class from a recognized IACS member society.

No valid class → no legitimate P&I insurance → oil spill liability gap.
This rule catches shadow fleet vessels that have lost class but may not yet
appear on sanctions lists.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule


class IACSClassStatusRule(ScoringRule):
    """Fire when IACS tracker data indicates classification risk."""

    @property
    def rule_id(self) -> str:
        return "iacs_class_status"

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

        # Need IMO to look up IACS data
        imo = profile.get("imo")
        if not imo:
            return None

        # Get IACS data from the profile's classification_data or iacs_data
        iacs_data = profile.get("iacs_data")
        if not iacs_data:
            return None

        findings: list[dict[str, Any]] = []
        max_severity = "low"
        total_points = 0.0

        status = iacs_data.get("status", "")
        risk_signal = iacs_data.get("risk_signal", "none")
        reason = iacs_data.get("reason", "")
        class_society = iacs_data.get("class_society")
        changes = iacs_data.get("changes", [])

        # --- 1. No IACS class at all (15 pts moderate) ---
        if status == "NO_IACS_CLASS":
            findings.append({
                "check": "no_iacs_class",
                "severity": "moderate",
                "points": 15,
                "reason": "Vessel has no record in any IACS classification society",
            })
            total_points += 15
            max_severity = _escalate(max_severity, "moderate")

        # --- 2. Withdrawn by society (25 pts critical) ---
        elif status == "Withdrawn" and "by society" in reason.lower():
            findings.append({
                "check": "class_withdrawn_by_society",
                "severity": "critical",
                "points": 25,
                "class_society": class_society,
                "reason": f"Classification withdrawn by {class_society}: {reason}",
            })
            total_points += 25
            max_severity = "critical"

        # --- 3. Withdrawn — non-compliance (20 pts high) ---
        elif status == "Withdrawn" and "non-compliance" in reason.lower():
            findings.append({
                "check": "class_withdrawn_noncompliance",
                "severity": "high",
                "points": 20,
                "class_society": class_society,
                "reason": f"Classification withdrawn for non-compliance: {reason}",
            })
            total_points += 20
            max_severity = _escalate(max_severity, "high")

        # --- 4. Withdrawn — survey overdue (20 pts high) ---
        elif status == "Withdrawn" and "survey overdue" in reason.lower():
            findings.append({
                "check": "class_withdrawn_survey_overdue",
                "severity": "high",
                "points": 20,
                "class_society": class_society,
                "reason": f"Classification withdrawn — survey overdue ({class_society})",
            })
            total_points += 20
            max_severity = _escalate(max_severity, "high")

        # --- 5. Withdrawn — other reasons (15 pts high) ---
        elif status == "Withdrawn":
            findings.append({
                "check": "class_withdrawn_other",
                "severity": "high",
                "points": 15,
                "class_society": class_society,
                "reason": f"Classification withdrawn from {class_society}: {reason or 'unknown reason'}",
            })
            total_points += 15
            max_severity = _escalate(max_severity, "high")

        # --- 6. Suspended (20 pts high) ---
        elif status == "Suspended":
            findings.append({
                "check": "class_suspended",
                "severity": "high",
                "points": 20,
                "class_society": class_society,
                "reason": f"Classification suspended by {class_society}: {reason}",
            })
            total_points += 20
            max_severity = _escalate(max_severity, "high")

        # --- 7. Vessel disappeared from IACS file (15 pts high) ---
        elif status == "Removed":
            findings.append({
                "check": "vessel_removed_from_iacs",
                "severity": "high",
                "points": 15,
                "reason": "Vessel disappeared from IACS Vessels-in-Class file",
            })
            total_points += 15
            max_severity = _escalate(max_severity, "high")

        # --- 8. Check for recent high-risk changes (additional 10 pts) ---
        if changes:
            thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
            recent_hr = [
                c for c in changes
                if c.get("is_high_risk")
                and _parse_dt(c.get("detected_at")) is not None
                and _parse_dt(c.get("detected_at")) > thirty_days_ago
            ]
            if recent_hr:
                # Recent status change to Withdrawn/Suspended
                status_changes = [c for c in recent_hr if c.get("change_type") == "status_change"]
                if status_changes:
                    findings.append({
                        "check": "recent_class_status_change",
                        "severity": "high",
                        "points": 10,
                        "changes": len(status_changes),
                        "reason": f"Classification status changed in last 30 days ({len(status_changes)} change(s))",
                    })
                    total_points += 10
                    max_severity = _escalate(max_severity, "high")

                # Name change detected
                name_changes = [c for c in recent_hr if c.get("change_type") == "name_change"]
                if name_changes:
                    old_name = name_changes[0].get("old_value", "?")
                    new_name = name_changes[0].get("new_value", "?")
                    findings.append({
                        "check": "iacs_name_change",
                        "severity": "moderate",
                        "points": 8,
                        "old_name": old_name,
                        "new_name": new_name,
                        "reason": f"Vessel name changed in IACS records: {old_name} → {new_name}",
                    })
                    total_points += 8
                    max_severity = _escalate(max_severity, "moderate")

        # --- No findings ---
        if not findings:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # --- Escalation for multiple findings ---
        if len(findings) >= 2:
            max_severity = _escalate(max_severity, "high")

        return RuleResult(
            fired=True,
            rule_id=self.rule_id,
            severity=max_severity,
            points=total_points,
            details={
                "findings": findings,
                "finding_count": len(findings),
                "iacs_status": status,
                "class_society": class_society,
                "risk_signal": risk_signal,
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
        """End anomaly if IACS status has improved (e.g. Reinstated)."""
        result = await self.evaluate(mmsi, profile, recent_positions, [], [])
        if result is None or not result.fired:
            return True
        # Check if the specific findings have changed
        old_details = active_anomaly.get("details", {})
        if isinstance(old_details, str):
            import json as _json
            old_details = _json.loads(old_details)
        old_checks = {f["check"] for f in old_details.get("findings", []) if isinstance(f, dict)}
        new_checks = {f["check"] for f in result.details.get("findings", []) if isinstance(f, dict)}
        if not old_checks.issubset(new_checks):
            return True
        return False


def _parse_dt(val: Any) -> datetime | None:
    """Parse a datetime from various formats."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None


_SEVERITY_ORDER = {"low": 0, "moderate": 1, "high": 2, "critical": 3}


def _escalate(current: str, candidate: str) -> str:
    if _SEVERITY_ORDER.get(candidate, 0) > _SEVERITY_ORDER.get(current, 0):
        return candidate
    return current
