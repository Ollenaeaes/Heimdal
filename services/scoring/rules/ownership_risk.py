"""Ownership Risk scoring rule.

Scores vessels based on their ownership structure. Evaluates factors such as
single-vessel companies, recently incorporated entities, high-risk jurisdiction
registrations, frequent ownership changes, and opaque ownership structures.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule

HIGH_RISK_OWNERSHIP_JURISDICTIONS: frozenset[str] = frozenset({
    "CM",  # Cameroon
    "KM",  # Comoros
    "GA",  # Gabon
    "PW",  # Palau
    "TZ",  # Tanzania
    "TG",  # Togo
    "GM",  # Gambia
    "SL",  # Sierra Leone
})

# Ship type range for tankers (AIS ship type codes 80-89)
_TANKER_TYPE_MIN = 80
_TANKER_TYPE_MAX = 89


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_tanker(profile: dict[str, Any]) -> bool:
    ship_type = profile.get("ship_type")
    if ship_type is None:
        return False
    try:
        return _TANKER_TYPE_MIN <= int(ship_type) <= _TANKER_TYPE_MAX
    except (ValueError, TypeError):
        return False


def _parse_ownership_data(raw: Any) -> dict[str, Any] | None:
    """Parse ownership_data from either a dict or a JSON string."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return None


class OwnershipRiskRule(ScoringRule):
    """Fire when a vessel's ownership structure indicates elevated risk."""

    @property
    def rule_id(self) -> str:
        return "ownership_risk"

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

        ownership_data = _parse_ownership_data(profile.get("ownership_data"))

        # Track individual risk factors
        factors: list[dict[str, Any]] = []

        if ownership_data is None:
            # No ownership data at all → opaque ownership
            factors.append({
                "factor": "opaque_ownership",
                "severity": "moderate",
                "points": 8,
                "reason": "No ownership data available",
            })
            # With no data we can only report this single factor
            return self._build_result(factors)

        owners = ownership_data.get("owners") or []
        history = ownership_data.get("history") or []
        now = _utcnow()

        # 1. Single-vessel company
        if ownership_data.get("single_vessel_company") is True:
            factors.append({
                "factor": "single_vessel_company",
                "severity": "moderate",
                "points": 8,
                "reason": "Owner operates a single-vessel company",
            })
        else:
            # Also check fleet_size on individual owners
            for owner in owners:
                if owner.get("fleet_size") == 1:
                    factors.append({
                        "factor": "single_vessel_company",
                        "severity": "moderate",
                        "points": 8,
                        "reason": f"Owner '{owner.get('name', 'unknown')}' has fleet_size=1",
                    })
                    break

        # 2. Recently incorporated (< 2 years)
        for owner in owners:
            inc_date_raw = owner.get("incorporated_date")
            if inc_date_raw is None:
                continue
            try:
                if isinstance(inc_date_raw, str):
                    inc_date = datetime.fromisoformat(inc_date_raw.replace("Z", "+00:00"))
                elif isinstance(inc_date_raw, datetime):
                    inc_date = inc_date_raw
                else:
                    continue
                if inc_date.tzinfo is None:
                    inc_date = inc_date.replace(tzinfo=timezone.utc)
                age_days = (now - inc_date).days
                if age_days < 730:  # ~2 years
                    factors.append({
                        "factor": "recently_incorporated",
                        "severity": "moderate",
                        "points": 8,
                        "reason": f"Owner incorporated {age_days} days ago",
                    })
                    break
            except (ValueError, TypeError):
                continue

        # 3. High-risk jurisdiction (only escalates to high if vessel is a tanker)
        is_tanker = _is_tanker(profile)
        for owner in owners:
            country = (owner.get("country") or "").strip().upper()
            if country in HIGH_RISK_OWNERSHIP_JURISDICTIONS:
                if is_tanker:
                    factors.append({
                        "factor": "high_risk_jurisdiction",
                        "severity": "high",
                        "points": 15,
                        "reason": f"Owner in {country} and vessel is a tanker",
                    })
                else:
                    factors.append({
                        "factor": "high_risk_jurisdiction",
                        "severity": "moderate",
                        "points": 8,
                        "reason": f"Owner in {country} (non-tanker)",
                    })
                break

        # 4. Frequent ownership changes (>1 in 12 months)
        twelve_months_ago = now.timestamp() - (365 * 24 * 3600)
        recent_changes = 0
        for entry in history:
            if entry.get("change") == "owner_changed":
                change_date_raw = entry.get("date")
                if change_date_raw is None:
                    continue
                try:
                    if isinstance(change_date_raw, str):
                        change_date = datetime.fromisoformat(
                            change_date_raw.replace("Z", "+00:00")
                        )
                    elif isinstance(change_date_raw, datetime):
                        change_date = change_date_raw
                    else:
                        continue
                    if change_date.tzinfo is None:
                        change_date = change_date.replace(tzinfo=timezone.utc)
                    if change_date.timestamp() >= twelve_months_ago:
                        recent_changes += 1
                except (ValueError, TypeError):
                    continue

        if recent_changes > 1:
            factors.append({
                "factor": "frequent_ownership_changes",
                "severity": "high",
                "points": 15,
                "reason": f"{recent_changes} ownership changes in 12 months",
            })

        # 5. Opaque ownership — no beneficial ownership info
        ownership_status = ownership_data.get("ownership_status")
        if ownership_status != "verified" and not owners:
            factors.append({
                "factor": "opaque_ownership",
                "severity": "moderate",
                "points": 8,
                "reason": "No beneficial ownership info available",
            })

        if not factors:
            return RuleResult(fired=False, rule_id=self.rule_id)

        return self._build_result(factors)

    def _build_result(self, factors: list[dict[str, Any]]) -> RuleResult:
        """Build a RuleResult from the collected risk factors."""
        if not factors:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # 6. Combined factors: 2+ risk factors → escalate to critical (25 pts)
        if len(factors) >= 2:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="critical",
                points=25.0,
                details={
                    "factor_count": len(factors),
                    "factors": [f["factor"] for f in factors],
                    "reasons": [f["reason"] for f in factors],
                },
                source="realtime",
            )

        # Single factor — use its own severity and points
        factor = factors[0]
        return RuleResult(
            fired=True,
            rule_id=self.rule_id,
            severity=factor["severity"],
            points=float(factor["points"]),
            details={
                "factor": factor["factor"],
                "reason": factor["reason"],
            },
            source="realtime",
        )
