"""Destination Spoofing rule.

Detects vessels using suspicious or evasive destination fields in their
AIS transmissions — including vague placeholder phrases, sea-area names,
or frequent destination changes.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule

# Exact-match placeholders (case-insensitive)
_PLACEHOLDER_PATTERNS: set[str] = {
    "FOR ORDERS",
    "FOR ORDER",
    "TBN",
    "TBA",
}

# Sea-area names (case-insensitive substring match)
_SEA_AREA_PATTERNS: list[str] = [
    "CARIBBEAN SEA",
    "MEDITERRANEAN",
    "ATLANTIC",
    "PACIFIC",
    "INDIAN OCEAN",
]

# Destination change threshold
_CHANGE_THRESHOLD = 3
_CHANGE_WINDOW_DAYS = 7


def _utcnow() -> datetime:
    """Return current UTC time.  Extracted for easy patching in tests."""
    return datetime.now(timezone.utc)


class DestinationSpoofRule(ScoringRule):
    """Fire when the AIS destination field looks evasive or suspicious."""

    @property
    def rule_id(self) -> str:
        return "destination_spoof"

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

        destination = (profile.get("destination") or "").strip().upper()
        if not destination:
            return None

        # Check placeholder patterns (substring match — destination may have
        # port prefix like "EE TLL FOR ORDERS")
        for pattern in _PLACEHOLDER_PATTERNS:
            if pattern in destination:
                return RuleResult(
                    fired=True,
                    rule_id=self.rule_id,
                    severity="high",
                    points=40.0,
                    details={"destination": destination, "reason": "placeholder_destination"},
                    source="realtime",
                )

        # Check sea-area patterns
        for pattern in _SEA_AREA_PATTERNS:
            if pattern in destination:
                return RuleResult(
                    fired=True,
                    rule_id=self.rule_id,
                    severity="high",
                    points=40.0,
                    details={"destination": destination, "reason": "sea_area_destination"},
                    source="realtime",
                )

        # Check frequent destination changes via existing anomaly history
        change_count = self._count_recent_destination_changes(existing_anomalies)
        if change_count >= _CHANGE_THRESHOLD:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="moderate",
                points=15.0,
                details={
                    "destination": destination,
                    "reason": "frequent_destination_changes",
                    "changes_in_window": change_count,
                },
                source="realtime",
            )

        return RuleResult(fired=False, rule_id=self.rule_id)

    async def check_event_ended(
        self,
        mmsi: int,
        profile: dict[str, Any] | None,
        recent_positions: Sequence[dict[str, Any]],
        active_anomaly: dict[str, Any],
    ) -> bool:
        """End when destination changes from a placeholder/sea-area to a real port name."""
        if not profile:
            return False
        destination = (profile.get("destination") or "").strip().upper()
        if not destination:
            return False

        # Check if the current destination is still a placeholder
        for pattern in _PLACEHOLDER_PATTERNS:
            if pattern in destination:
                return False  # still a placeholder

        # Check if the current destination is still a sea area
        for pattern in _SEA_AREA_PATTERNS:
            if pattern in destination:
                return False  # still a sea area

        # If we get here, the destination looks like a real port name
        return True

    # ------------------------------------------------------------------

    @staticmethod
    def _count_recent_destination_changes(
        existing_anomalies: Sequence[dict[str, Any]],
    ) -> int:
        """Count distinct destination_spoof anomalies in the last 7 days.

        Each previous firing with a different destination in its details
        counts as one change.
        """
        now = _utcnow()
        cutoff = now - timedelta(days=_CHANGE_WINDOW_DAYS)
        destinations: set[str] = set()

        for a in existing_anomalies:
            if a.get("rule_id") != "destination_spoof":
                continue
            created = a.get("created_at")
            if created is None:
                continue
            if isinstance(created, str):
                created = datetime.fromisoformat(created)
            if not created.tzinfo:
                created = created.replace(tzinfo=timezone.utc)
            if created < cutoff:
                continue
            details = a.get("details", {})
            if isinstance(details, str):
                import json
                details = json.loads(details)
            dest = details.get("destination", "")
            if dest:
                destinations.add(dest)

        return len(destinations)
