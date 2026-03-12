"""GFW Dark SAR scoring rule.

Fires when a dark SAR detection (is_dark=true) correlates with an
existing real-time ``ais_gap`` anomaly within a 48-hour window.

This rule queries the ``sar_detections`` table directly because SAR
data is not part of the standard ``gfw_events`` feed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.connection import get_session
from shared.models.anomaly import RuleResult

from rules.base import ScoringRule

# Correlation window: SAR detection must be within 48 h of an AIS gap
_CORRELATION_WINDOW = timedelta(hours=48)


class GfwDarkSarRule(ScoringRule):
    """Dark SAR detection correlated with AIS gap."""

    @property
    def rule_id(self) -> str:
        return "gfw_dark_sar"

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
        # Step 1: Query sar_detections for dark detections matching this MMSI
        dark_detections = await self._get_dark_sar_detections(mmsi)

        if not dark_detections:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Step 2: Check existing anomalies for ais_gap within 48h window
        ais_gap_anomalies = [
            a for a in existing_anomalies
            if a.get("rule_id") == "ais_gap" and not a.get("resolved", False)
        ]

        if not ais_gap_anomalies:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # Step 3: Check temporal correlation
        for detection in dark_detections:
            det_time = detection.get("detection_time")
            if det_time is None:
                continue
            # Ensure timezone-aware
            if isinstance(det_time, datetime) and det_time.tzinfo is None:
                det_time = det_time.replace(tzinfo=timezone.utc)

            for gap in ais_gap_anomalies:
                gap_time = gap.get("created_at")
                if gap_time is None:
                    continue
                if isinstance(gap_time, datetime) and gap_time.tzinfo is None:
                    gap_time = gap_time.replace(tzinfo=timezone.utc)

                if abs(det_time - gap_time) <= _CORRELATION_WINDOW:
                    return RuleResult(
                        fired=True,
                        rule_id=self.rule_id,
                        severity="high",
                        points=40.0,
                        details={
                            "event_type": "DARK_SAR",
                            "detection_time": str(det_time),
                            "ais_gap_created_at": str(gap_time),
                            "lat": detection.get("lat"),
                            "lon": detection.get("lon"),
                            "reason": "Dark SAR detection correlated with AIS gap",
                        },
                        source="gfw",
                    )

        return RuleResult(fired=False, rule_id=self.rule_id)

    async def _get_dark_sar_detections(
        self, mmsi: int
    ) -> list[dict[str, Any]]:
        """Query sar_detections for dark detections matching *mmsi*."""
        session_factory = get_session()
        async with session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT
                        id, detection_time,
                        ST_Y(position::geometry) AS lat,
                        ST_X(position::geometry) AS lon,
                        is_dark, matched_mmsi, confidence
                    FROM sar_detections
                    WHERE matched_mmsi = :mmsi
                      AND is_dark = true
                    ORDER BY detection_time DESC
                    LIMIT 10
                """),
                {"mmsi": mmsi},
            )
            return [dict(r) for r in result.mappings().all()]
