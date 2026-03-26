"""Sanctions Match rule.

Checks whether a vessel's ``sanctions_status`` JSONB field contains
matches from the enrichment pipeline.  Scoring depends on both the
program type and how the match was made:

- Sanctions list + IMO/MMSI match → critical (100 pts)
- Sanctions list + name match → moderate (15 pts)
- MoU detention / PSC + IMO/MMSI match → high (40 pts)
- MoU detention / PSC + name match → moderate (15 pts)
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule

# Programs that represent actual sanctions lists
_SANCTIONS_PROGRAMS = frozenset({
    "sanctions",
    "ua_war_sanctions",
    "eu_sanctions_map",
    "eu_journal_sanctions",
    "gb_fcdo_sanctions",
    "ca_dfatd_sema_sanctions",
    "ch_seco_sanctions",
    "us_sam_exclusions",
    "kp_rusi_reports",
})


class SanctionsMatchRule(ScoringRule):
    """Fire when the vessel matches a sanctions or detention list entity."""

    @property
    def rule_id(self) -> str:
        return "sanctions_match"

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

        sanctions = profile.get("sanctions_status")
        if not sanctions:
            return RuleResult(fired=False, rule_id=self.rule_id)

        if isinstance(sanctions, str):
            import json
            sanctions = json.loads(sanctions)

        matches = sanctions.get("matches", [])
        if not matches:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Find highest-confidence match
        best_match = max(matches, key=lambda m: m.get("confidence", 0))
        confidence = best_match.get("confidence", 0)
        matched_field = best_match.get("matched_field", "")
        program = best_match.get("program", "unknown")

        if confidence <= 0:
            return RuleResult(fired=False, rule_id=self.rule_id)

        is_identifier_match = matched_field in ("imo", "mmsi")
        is_sanctions = program in _SANCTIONS_PROGRAMS

        if is_identifier_match and is_sanctions:
            severity, points, match_type = "critical", 100.0, "direct_sanctions"
        elif is_identifier_match:
            # MoU detention, PSC, etc. — confirmed vessel but lower severity
            severity, points, match_type = "high", 40.0, "direct_detention"
        else:
            # Name-only match — needs human verification regardless of program
            severity, points, match_type = "moderate", 15.0, "name_only"

        return RuleResult(
            fired=True,
            rule_id=self.rule_id,
            severity=severity,
            points=points,
            details={
                "confidence": confidence,
                "matched_field": matched_field,
                "program": program,
                "entity_id": best_match.get("entity_id"),
                "match_type": match_type,
            },
            source="realtime",
        )
