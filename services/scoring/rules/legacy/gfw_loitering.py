"""GFW Loitering scoring rule.

Fires when a GFW ``LOITERING`` event is found for the vessel.
Severity depends on whether the loitering occurred in an STS zone.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from shared.db.connection import get_session
from shared.models.anomaly import RuleResult

from rules.base import ScoringRule
from rules.gfw_helpers import dedup_events, filter_already_seen, parse_start_time
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
        loitering_events = [
            e for e in gfw_events
            if str(e.get("event_type", "")).upper() == "LOITERING"
        ]

        if not loitering_events:
            return []

        # Sort by start_time, apply temporal dedup, filter already-seen
        loitering_events.sort(
            key=lambda e: parse_start_time(e) or datetime.min.replace(tzinfo=timezone.utc)
        )
        loitering_events = dedup_events(loitering_events)
        loitering_events = filter_already_seen(loitering_events, existing_anomalies)

        if not loitering_events:
            return []

        results: list[RuleResult] = []

        for event in loitering_events:
            lat = event.get("lat")
            lon = event.get("lon")
            gfw_event_id = event.get("gfw_event_id")

            in_sts = False
            zone_name: str | None = None

            if lat is not None and lon is not None:
                session_factory = get_session()
                async with session_factory() as session:
                    zone_name = await is_in_sts_zone(session, lat, lon)
                    in_sts = zone_name is not None

            if in_sts:
                results.append(RuleResult(
                    fired=True,
                    rule_id=self.rule_id,
                    severity="high",
                    points=40.0,
                    details={
                        "event_type": "LOITERING",
                        "gfw_event_id": gfw_event_id,
                        "lat": lat,
                        "lon": lon,
                        "zone": zone_name,
                        "reason": "Loitering in STS zone",
                    },
                    source="gfw",
                ))
            else:
                results.append(RuleResult(
                    fired=True,
                    rule_id=self.rule_id,
                    severity="moderate",
                    points=15.0,
                    details={
                        "event_type": "LOITERING",
                        "gfw_event_id": gfw_event_id,
                        "lat": lat,
                        "lon": lon,
                        "reason": "Loitering in open ocean",
                    },
                    source="gfw",
                ))

        return results
