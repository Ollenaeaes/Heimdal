"""Sanctions Match rule.

Checks whether a vessel's ``sanctions_status`` JSONB field contains
matches from the enrichment pipeline.  A direct IMO/MMSI match (high
confidence) is critical; a fuzzy name match is high severity.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule

_DIRECT_MATCH_THRESHOLD = 0.8


class SanctionsMatchRule(ScoringRule):
    """Fire when the vessel matches a sanctions list entity."""

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

        if confidence >= _DIRECT_MATCH_THRESHOLD:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="critical",
                points=100.0,
                details={
                    "confidence": confidence,
                    "matched_field": best_match.get("matched_field"),
                    "program": best_match.get("program"),
                    "entity_id": best_match.get("entity_id"),
                    "match_type": "direct",
                },
                source="realtime",
            )

        # Lower confidence = fuzzy name match
        if confidence > 0:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="high",
                points=40.0,
                details={
                    "confidence": confidence,
                    "matched_field": best_match.get("matched_field"),
                    "program": best_match.get("program"),
                    "entity_id": best_match.get("entity_id"),
                    "match_type": "fuzzy",
                },
                source="realtime",
            )

        return RuleResult(fired=False, rule_id=self.rule_id)
