"""GFW Encounter scoring rule.

Fires when a GFW ``ENCOUNTER`` event is found for the vessel.
Severity depends on whether the encounter occurred in an STS zone or
involved a sanctioned partner vessel.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from shared.db.connection import get_session
from shared.models.anomaly import RuleResult

from rules.base import ScoringRule
from rules.gfw_helpers import dedup_events, filter_already_seen, parse_start_time
from rules.zone_helpers import is_in_sts_zone


class GfwEncounterRule(ScoringRule):
    """Ship-to-ship encounter detected via Global Fishing Watch."""

    @property
    def rule_id(self) -> str:
        return "gfw_encounter"

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
        return RuleResult(fired=False, rule_id=self.rule_id)

    async def evaluate_all(
        self,
        mmsi: int,
        profile: dict[str, Any] | None,
        recent_positions: Sequence[dict[str, Any]],
        existing_anomalies: Sequence[dict[str, Any]],
        gfw_events: Sequence[dict[str, Any]],
    ) -> list[RuleResult]:
        encounter_events = [
            e for e in gfw_events
            if str(e.get("event_type", "")).upper() == "ENCOUNTER"
        ]

        if not encounter_events:
            return []

        # Sort by start_time, apply temporal dedup, filter already-seen
        encounter_events.sort(
            key=lambda e: parse_start_time(e) or datetime.min.replace(tzinfo=timezone.utc)
        )
        encounter_events = dedup_events(encounter_events)
        encounter_events = filter_already_seen(encounter_events, existing_anomalies)

        if not encounter_events:
            return []

        results: list[RuleResult] = []

        for event in encounter_events:
            lat = event.get("lat")
            lon = event.get("lon")
            encounter_mmsi = event.get("encounter_mmsi")
            gfw_event_id = event.get("gfw_event_id")

            in_sts_zone = False
            zone_name: str | None = None

            if lat is not None and lon is not None:
                session_factory = get_session()
                async with session_factory() as session:
                    zone_name = await is_in_sts_zone(session, lat, lon)
                    in_sts_zone = zone_name is not None

            # Check if encounter partner is sanctioned via event details
            partner_sanctioned = False
            event_details = event.get("details") or {}
            if isinstance(event_details, dict):
                partner_sanctioned = bool(event_details.get("partner_sanctioned"))

            if in_sts_zone or partner_sanctioned:
                results.append(RuleResult(
                    fired=True,
                    rule_id=self.rule_id,
                    severity="critical",
                    points=100.0,
                    details={
                        "event_type": "ENCOUNTER",
                        "gfw_event_id": gfw_event_id,
                        "lat": lat,
                        "lon": lon,
                        "encounter_mmsi": encounter_mmsi,
                        "zone": zone_name,
                        "partner_sanctioned": partner_sanctioned,
                        "reason": "Encounter in STS zone or with sanctioned partner",
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
                        "event_type": "ENCOUNTER",
                        "gfw_event_id": gfw_event_id,
                        "lat": lat,
                        "lon": lon,
                        "encounter_mmsi": encounter_mmsi,
                        "reason": "Encounter outside STS zone, non-sanctioned partner",
                    },
                    source="gfw",
                ))

        return results
