"""GFW Port Visit scoring rule.

Fires when a GFW ``PORT_VISIT`` event indicates a visit to a known
Russian terminal.  Non-Russian port visits do not fire.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from rules.base import ScoringRule
from rules.gfw_helpers import dedup_events, filter_already_seen, parse_start_time
from rules.zone_helpers import is_russian_terminal_port


class GfwPortVisitRule(ScoringRule):
    """Port visit at a Russian terminal detected via Global Fishing Watch."""

    @property
    def rule_id(self) -> str:
        return "gfw_port_visit"

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
        # Filter to Russian port visits only (non-Russian never fire)
        port_visits = [
            e for e in gfw_events
            if str(e.get("event_type", "")).upper() == "PORT_VISIT"
            and is_russian_terminal_port(e.get("port_name"))
        ]

        if not port_visits:
            return []

        # Sort by start_time, apply temporal dedup, filter already-seen
        port_visits.sort(
            key=lambda e: parse_start_time(e) or datetime.min.replace(tzinfo=timezone.utc)
        )
        port_visits = dedup_events(port_visits)
        port_visits = filter_already_seen(port_visits, existing_anomalies)

        if not port_visits:
            return []

        results: list[RuleResult] = []

        for event in port_visits:
            port_name = event.get("port_name")
            gfw_event_id = event.get("gfw_event_id")
            results.append(RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="high",
                points=40.0,
                details={
                    "event_type": "PORT_VISIT",
                    "gfw_event_id": gfw_event_id,
                    "port_name": port_name,
                    "lat": event.get("lat"),
                    "lon": event.get("lon"),
                    "reason": f"Port visit at Russian terminal: {port_name}",
                },
                source="gfw",
            ))

        return results
