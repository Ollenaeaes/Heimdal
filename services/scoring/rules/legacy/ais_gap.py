"""AIS Gap Detection rule.

Detects vessels that have gone silent — no AIS position received for an
extended period.  Uses ``profile['last_position_time']`` to determine
the gap duration relative to *now*.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult

from .base import ScoringRule

# Gap thresholds (hours) and their severity / points
_THRESHOLDS: list[tuple[float, str, float]] = [
    (48.0, "high", 40.0),
    (12.0, "moderate", 15.0),
    (2.0, "low", 5.0),
]

# Cooldown: don't re-fire within 24 hours of the last ais_gap anomaly
_COOLDOWN_HOURS = 24.0


def _utcnow() -> datetime:
    """Return current UTC time.  Extracted for easy patching in tests."""
    return datetime.now(timezone.utc)


class AisGapRule(ScoringRule):
    """Fire when a vessel's last AIS position exceeds a time threshold."""

    @property
    def rule_id(self) -> str:
        return "ais_gap"

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
        now = _utcnow()

        # Determine last-seen time from profile or recent positions
        last_seen = self._get_last_seen(profile, recent_positions)
        if last_seen is None:
            return None  # no data to evaluate

        gap_hours = (now - last_seen).total_seconds() / 3600.0

        # Check cooldown: skip if ais_gap fired within 24 h
        if self._is_on_cooldown(existing_anomalies, now):
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Evaluate against thresholds (largest first)
        for threshold_hours, severity, points in _THRESHOLDS:
            if gap_hours >= threshold_hours:
                return RuleResult(
                    fired=True,
                    rule_id=self.rule_id,
                    severity=severity,
                    points=points,
                    details={
                        "gap_hours": round(gap_hours, 2),
                        "last_seen": last_seen.isoformat(),
                        "threshold_hours": threshold_hours,
                    },
                    source="realtime",
                )

        # Gap < 2 h — does not fire
        return RuleResult(fired=False, rule_id=self.rule_id)

    async def check_event_ended(
        self,
        mmsi: int,
        profile: dict[str, Any] | None,
        recent_positions: Sequence[dict[str, Any]],
        active_anomaly: dict[str, Any],
    ) -> bool:
        """End when a new position is received (signal resumed).

        If recent_positions has a position newer than the anomaly's
        event_start, the gap is over.
        """
        # Determine when the gap started
        event_start = active_anomaly.get("event_start") or active_anomaly.get("created_at")
        if event_start is None:
            return False
        if isinstance(event_start, str):
            event_start = datetime.fromisoformat(event_start)
        if not event_start.tzinfo:
            event_start = event_start.replace(tzinfo=timezone.utc)

        # Check if any recent position is newer than event_start
        for pos in recent_positions:
            ts = pos.get("timestamp")
            if ts is None:
                continue
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            if not ts.tzinfo:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts > event_start:
                return True
        return False

    # ------------------------------------------------------------------

    @staticmethod
    def _get_last_seen(
        profile: dict[str, Any] | None,
        recent_positions: Sequence[dict[str, Any]],
    ) -> Optional[datetime]:
        """Derive the most recent position timestamp."""
        candidates: list[datetime] = []

        if profile and profile.get("last_position_time"):
            ts = profile["last_position_time"]
            if isinstance(ts, datetime):
                candidates.append(ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc))
            elif isinstance(ts, str):
                candidates.append(datetime.fromisoformat(ts).replace(tzinfo=timezone.utc))

        for pos in recent_positions:
            ts = pos.get("timestamp")
            if ts is None:
                continue
            if isinstance(ts, datetime):
                candidates.append(ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc))
            elif isinstance(ts, str):
                candidates.append(datetime.fromisoformat(ts).replace(tzinfo=timezone.utc))

        return max(candidates) if candidates else None

    @staticmethod
    def _is_on_cooldown(
        existing_anomalies: Sequence[dict[str, Any]],
        now: datetime,
    ) -> bool:
        """Return True if an ais_gap anomaly was created within the cooldown window."""
        for a in existing_anomalies:
            if a.get("rule_id") != "ais_gap":
                continue
            created = a.get("created_at")
            if created is None:
                continue
            if isinstance(created, str):
                created = datetime.fromisoformat(created)
            if not created.tzinfo:
                created = created.replace(tzinfo=timezone.utc)
            hours_ago = (now - created).total_seconds() / 3600.0
            if hours_ago < _COOLDOWN_HOURS:
                return True
        return False
