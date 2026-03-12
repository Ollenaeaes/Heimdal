"""GFW Loitering scoring rule.

Fires when a GFW ``LOITERING`` event is found for the vessel.
Severity depends on whether the loitering occurred in an STS zone.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from shared.db.connection import get_session
from shared.models.anomaly import RuleResult

from rules.base import ScoringRule
from rules.zone_helpers import is_in_sts_zone


class GfwLoiteringRule(ScoringRule):
    """Loitering detected via Global Fishing Watch."""

    @property
    def rule_id(self) -> str:
        return "gfw_loitering"

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
        loitering_events = [
            e for e in gfw_events
            if str(e.get("event_type", "")).upper() == "LOITERING"
        ]

        if not loitering_events:
            return RuleResult(fired=False, rule_id=self.rule_id)

        event = loitering_events[0]
        lat = event.get("lat")
        lon = event.get("lon")

        in_sts = False
        zone_name: str | None = None

        if lat is not None and lon is not None:
            session_factory = get_session()
            async with session_factory() as session:
                zone_name = await is_in_sts_zone(session, lat, lon)
                in_sts = zone_name is not None

        if in_sts:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="high",
                points=40.0,
                details={
                    "event_type": "LOITERING",
                    "lat": lat,
                    "lon": lon,
                    "zone": zone_name,
                    "reason": "Loitering in STS zone",
                },
                source="gfw",
            )

        return RuleResult(
            fired=True,
            rule_id=self.rule_id,
            severity="moderate",
            points=15.0,
            details={
                "event_type": "LOITERING",
                "lat": lat,
                "lon": lon,
                "reason": "Loitering in open ocean",
            },
            source="gfw",
        )
