"""GFW Port Visit scoring rule.

Fires when a GFW ``PORT_VISIT`` event indicates a visit to a known
Russian terminal.  Non-Russian port visits do not fire.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from rules.base import ScoringRule
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
        port_visits = [
            e for e in gfw_events
            if str(e.get("event_type", "")).upper() == "PORT_VISIT"
        ]

        if not port_visits:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Check each port visit for Russian terminal match
        for event in port_visits:
            port_name = event.get("port_name")
            if is_russian_terminal_port(port_name):
                return RuleResult(
                    fired=True,
                    rule_id=self.rule_id,
                    severity="high",
                    points=40.0,
                    details={
                        "event_type": "PORT_VISIT",
                        "port_name": port_name,
                        "lat": event.get("lat"),
                        "lon": event.get("lon"),
                        "reason": f"Port visit at Russian terminal: {port_name}",
                    },
                    source="gfw",
                )

        # Non-Russian port visits: rule does not fire
        return RuleResult(fired=False, rule_id=self.rule_id)
