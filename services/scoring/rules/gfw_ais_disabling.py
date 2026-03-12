"""GFW AIS-Disabling scoring rule.

Fires when a GFW ``AIS_DISABLING`` event is found for the vessel.
Severity depends on whether the event occurred in a sanctions-relevant
corridor (STS zone or near a Russian terminal).
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from shared.db.connection import get_session
from shared.models.anomaly import RuleResult

from rules.base import ScoringRule
from rules.zone_helpers import is_in_sts_zone, is_near_russian_terminal


class GfwAisDisablingRule(ScoringRule):
    """AIS disabling detected via Global Fishing Watch."""

    @property
    def rule_id(self) -> str:
        return "gfw_ais_disabling"

    @property
    def rule_category(self) -> str:
        return "gfw_sourced"

    async def evaluate(
        self,
        mmsi: int,
        profile: dict[str, Any] | None,
        recent_positions: Sequence[dict[str, Any]],
        existing_anomalies: Sequence[dict[str, Any]],
        gfw_events: Sequence[dict[str, Any]],
    ) -> Optional[RuleResult]:
        # Find AIS_DISABLING events
        disabling_events = [
            e for e in gfw_events
            if str(e.get("event_type", "")).upper() == "AIS_DISABLING"
        ]

        if not disabling_events:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Evaluate the most recent event
        event = disabling_events[0]
        lat = event.get("lat")
        lon = event.get("lon")

        in_corridor = False
        zone_name: str | None = None

        if lat is not None and lon is not None:
            session_factory = get_session()
            async with session_factory() as session:
                zone_name = await is_in_sts_zone(session, lat, lon)
                if zone_name is None:
                    zone_name = await is_near_russian_terminal(session, lat, lon)
                in_corridor = zone_name is not None

        if in_corridor:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="critical",
                points=100.0,
                details={
                    "event_type": "AIS_DISABLING",
                    "lat": lat,
                    "lon": lon,
                    "zone": zone_name,
                    "reason": "AIS disabling in sanctions corridor",
                },
                source="gfw",
            )

        return RuleResult(
            fired=True,
            rule_id=self.rule_id,
            severity="high",
            points=40.0,
            details={
                "event_type": "AIS_DISABLING",
                "lat": lat,
                "lon": lon,
                "reason": "AIS disabling outside known corridor",
            },
            source="gfw",
        )
