"""Voyage Pattern Analysis rule.

Detects canonical shadow fleet voyage patterns that indicate sanctions
evasion: Russian port → STS hotspot → India/China/Turkey destination.

Patterns detected:
- russian_port_to_sts: Russian port visit + current position in STS zone
- sts_to_destination: Position in STS zone + destination in shadow fleet list
- full_evasion_route: Complete chain (Russian port → STS → destination)
- suspicious_ballast: Low-draught ballast voyage heading toward STS zone
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule
from .gfw_helpers import parse_start_time
from .zone_helpers import is_russian_terminal_port

# Destinations commonly associated with shadow fleet oil deliveries.
SHADOW_FLEET_DESTINATIONS: frozenset[str] = frozenset({
    "SIKKA", "JAMNAGAR", "PARADIP", "VADINAR", "MUMBAI", "CHENNAI",
    "QINGDAO", "RIZHAO", "DONGYING", "ZHOUSHAN", "NINGBO",
    "ISKENDERUN", "MERSIN", "ALIAGA", "DORTYOL",
    "DALIAN", "CEYHAN",
})

# Look-back window for Russian port visits.
_PORT_VISIT_LOOKBACK_DAYS = 30

# Draught threshold (metres) below which a tanker is considered in ballast.
_BALLAST_DRAUGHT_THRESHOLD = 6.0

# Speed threshold (knots) — vessels transiting through an STS zone at high
# speed are NOT flagged (they are passing through, not loitering for STS).
_TRANSIT_SPEED_THRESHOLD = 8.0


class VoyagePatternRule(ScoringRule):
    """Detect sanctions-evasion voyage patterns."""

    @property
    def rule_id(self) -> str:
        return "voyage_pattern"

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
        # --- gather signals ------------------------------------------------
        has_russian_port = self._has_recent_russian_port_visit(gfw_events)

        latest_pos = self._get_latest_position(recent_positions)
        in_sts_zone = False
        sts_zone_name: Optional[str] = None
        if latest_pos is not None:
            sog = latest_pos.get("sog")
            # Vessel transiting at high speed through STS zone is not flagged
            if sog is not None and sog > _TRANSIT_SPEED_THRESHOLD:
                in_sts_zone = False
            else:
                sts_zone_name = await _check_position_sts_zone(latest_pos)
                in_sts_zone = sts_zone_name is not None

        destination = (profile or {}).get("destination") or ""
        dest_match = self._destination_matches(destination)

        # --- determine pattern (most severe first) -------------------------

        # Full evasion route: Russian port → STS zone → shadow fleet dest
        if has_russian_port and in_sts_zone and dest_match:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="critical",
                points=25.0,
                details={
                    "reason": "full_evasion_route",
                    "sts_zone": sts_zone_name,
                    "destination": destination,
                },
                source="gfw",
            )

        # Russian port → STS zone
        if has_russian_port and in_sts_zone:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="high",
                points=15.0,
                details={
                    "reason": "russian_port_to_sts",
                    "sts_zone": sts_zone_name,
                },
                source="gfw",
            )

        # STS zone → shadow fleet destination
        if in_sts_zone and dest_match:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="moderate",
                points=8.0,
                details={
                    "reason": "sts_to_destination",
                    "sts_zone": sts_zone_name,
                    "destination": destination,
                },
                source="gfw",
            )

        # Suspicious ballast: low draught + in/near STS zone
        if latest_pos is not None and in_sts_zone:
            draught = latest_pos.get("draught")
            if draught is not None and draught < _BALLAST_DRAUGHT_THRESHOLD:
                return RuleResult(
                    fired=True,
                    rule_id=self.rule_id,
                    severity="moderate",
                    points=8.0,
                    details={
                        "reason": "suspicious_ballast",
                        "draught": draught,
                        "sts_zone": sts_zone_name,
                    },
                    source="gfw",
                )

        return RuleResult(fired=False, rule_id=self.rule_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_recent_russian_port_visit(
        gfw_events: Sequence[dict[str, Any]],
    ) -> bool:
        """Check if any GFW PORT_VISIT at a Russian port occurred within 30 days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=_PORT_VISIT_LOOKBACK_DAYS)
        for event in gfw_events:
            if str(event.get("event_type", "")).upper() != "PORT_VISIT":
                continue
            if not is_russian_terminal_port(event.get("port_name")):
                continue
            start = parse_start_time(event)
            if start is not None and start >= cutoff:
                return True
        return False

    @staticmethod
    def _get_latest_position(
        positions: Sequence[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        """Return the most recent position by timestamp, or None."""
        if not positions:
            return None
        sorted_pos = sorted(positions, key=lambda p: p.get("timestamp", ""))
        return sorted_pos[-1]

    @staticmethod
    def _destination_matches(destination: str) -> bool:
        """Check if the destination string contains a shadow fleet port keyword."""
        if not destination:
            return False
        dest_upper = destination.upper()
        return any(kw in dest_upper for kw in SHADOW_FLEET_DESTINATIONS)


async def _check_position_sts_zone(
    position: dict[str, Any],
) -> Optional[str]:
    """DB-backed STS zone check for a single position.

    Extracted as a module-level function so tests can patch it easily.
    """
    lat, lon = position.get("lat"), position.get("lon")
    if lat is None or lon is None:
        return None

    from shared.db.connection import get_session
    from .zone_helpers import is_in_sts_zone

    async with get_session() as session:
        return await is_in_sts_zone(session, lat, lon)
