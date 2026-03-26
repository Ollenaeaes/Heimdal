"""GFW AIS-Disabling scoring rule.

Fires when a GFW ``AIS_DISABLING`` event is found for the vessel.
Severity depends on whether the event occurred in a sanctions-relevant
corridor (STS zone or near a Russian terminal).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from shared.db.connection import get_session
from shared.models.anomaly import RuleResult

from rules.base import ScoringRule
from rules.gfw_helpers import dedup_events, filter_already_seen, parse_start_time
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
        results = await self.evaluate_all(
            mmsi, profile, recent_positions, existing_anomalies, gfw_events,
        )
        if results:
            return results[0]
        # Check if there are any AIS_DISABLING events at all for proper
        # backward-compatible "fired=False" return.
        disabling_events = [
            e for e in gfw_events
            if str(e.get("event_type", "")).upper() == "AIS_DISABLING"
        ]
        if not disabling_events:
            return RuleResult(fired=False, rule_id=self.rule_id)
        # Events existed but were all deduped against existing anomalies.
        return RuleResult(fired=False, rule_id=self.rule_id)

    async def evaluate_all(
        self,
        mmsi: int,
        profile: dict[str, Any] | None,
        recent_positions: Sequence[dict[str, Any]],
        existing_anomalies: Sequence[dict[str, Any]],
        gfw_events: Sequence[dict[str, Any]],
    ) -> list[RuleResult]:
        # Filter to AIS_DISABLING events only
        disabling_events = [
            e for e in gfw_events
            if str(e.get("event_type", "")).upper() == "AIS_DISABLING"
        ]

        if not disabling_events:
            return []

        # Sort by start_time, apply temporal dedup, filter already-seen
        disabling_events.sort(
            key=lambda e: parse_start_time(e) or datetime.min.replace(tzinfo=timezone.utc)
        )
        disabling_events = dedup_events(disabling_events)
        disabling_events = filter_already_seen(disabling_events, existing_anomalies)

        if not disabling_events:
            return []

        results: list[RuleResult] = []

        for event in disabling_events:
            lat = event.get("lat")
            lon = event.get("lon")
            gfw_event_id = event.get("gfw_event_id")

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
                results.append(RuleResult(
                    fired=True,
                    rule_id=self.rule_id,
                    severity="critical",
                    points=100.0,
                    details={
                        "event_type": "AIS_DISABLING",
                        "gfw_event_id": gfw_event_id,
                        "lat": lat,
                        "lon": lon,
                        "zone": zone_name,
                        "reason": "AIS disabling in sanctions corridor",
                    },
                    source="gfw",
                ))
            else:
                results.append(RuleResult(
                    fired=True,
                    rule_id=self.rule_id,
                    severity="high",
                    points=40.0,
                    details={
                        "event_type": "AIS_DISABLING",
                        "gfw_event_id": gfw_event_id,
                        "lat": lat,
                        "lon": lon,
                        "reason": "AIS disabling outside known corridor",
                    },
                    source="gfw",
                ))

        return results
