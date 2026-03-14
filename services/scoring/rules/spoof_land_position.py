"""Spoofing detection: position on land.

Fires when a vessel's AIS position falls within a land polygon,
with a 100m coastline buffer exclusion to avoid false positives
for vessels near shore.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from sqlalchemy import text

from shared.db import get_session
from shared.models.anomaly import RuleResult

from .base import ScoringRule

logger = logging.getLogger(__name__)

# Coastline buffer in metres — positions within this distance of the coast
# are excluded to avoid false positives from GPS inaccuracy near shore.
_COASTLINE_BUFFER_M = 100


class SpoofLandPositionRule(ScoringRule):
    """Fire when a vessel reports a position on land."""

    @property
    def rule_id(self) -> str:
        return "spoof_land_position"

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
        if not recent_positions:
            return None

        # Check if land_mask table has data
        has_land_data = await self._has_land_mask_data()
        if not has_land_data:
            logger.warning(
                "land_mask table is empty — skipping spoof_land_position rule "
                "for MMSI %s", mmsi,
            )
            return None

        sorted_pos = sorted(recent_positions, key=lambda p: p.get("timestamp", ""))

        # Check each position for land intersection
        land_positions: list[dict[str, Any]] = []
        for pos in sorted_pos:
            lat = pos.get("lat")
            lon = pos.get("lon")
            if lat is None or lon is None:
                continue

            on_land = await self._is_on_land(lat, lon)
            if on_land:
                land_positions.append(pos)

        if not land_positions:
            return RuleResult(fired=False, rule_id=self.rule_id)

        # 3+ consecutive land positions → critical
        consecutive = self._count_max_consecutive_land(sorted_pos, land_positions)

        if consecutive >= 3:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="critical",
                points=100.0,
                details={
                    "reason": "consecutive_land_positions",
                    "land_position_count": len(land_positions),
                    "max_consecutive": consecutive,
                    "latest_land_lat": land_positions[-1].get("lat"),
                    "latest_land_lon": land_positions[-1].get("lon"),
                },
                source="realtime",
            )

        # Single land position → moderate
        return RuleResult(
            fired=True,
            rule_id=self.rule_id,
            severity="moderate",
            points=15.0,
            details={
                "reason": "land_position",
                "land_position_count": len(land_positions),
                "max_consecutive": consecutive,
                "latest_land_lat": land_positions[-1].get("lat"),
                "latest_land_lon": land_positions[-1].get("lon"),
            },
            source="realtime",
        )

    def _count_max_consecutive_land(
        self,
        all_positions: Sequence[dict[str, Any]],
        land_positions: list[dict[str, Any]],
    ) -> int:
        """Count the maximum number of consecutive positions that are on land."""
        land_set = {id(p) for p in land_positions}
        max_run = 0
        current_run = 0
        for pos in all_positions:
            if id(pos) in land_set:
                current_run += 1
                max_run = max(max_run, current_run)
            else:
                current_run = 0
        return max_run

    async def _has_land_mask_data(self) -> bool:
        """Check if the land_mask table has any rows."""
        session_factory = get_session()
        async with session_factory() as session:
            result = await session.execute(
                text("SELECT EXISTS(SELECT 1 FROM land_mask LIMIT 1)")
            )
            row = result.scalar()
            return bool(row)

    async def _is_on_land(self, lat: float, lon: float) -> bool:
        """Check if a lat/lon position is on land (beyond coastal buffer)."""
        session_factory = get_session()
        async with session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT EXISTS(
                        SELECT 1 FROM land_mask
                        WHERE ST_Intersects(
                            geometry,
                            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                        )
                        AND ST_Distance(
                            geometry,
                            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                        ) = 0
                        AND NOT EXISTS(
                            SELECT 1 FROM land_mask lm2
                            WHERE ST_DWithin(
                                ST_Boundary(lm2.geometry::geometry)::geography,
                                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                                :buffer
                            )
                        )
                    )
                """),
                {"lat": lat, "lon": lon, "buffer": _COASTLINE_BUFFER_M},
            )
            return bool(result.scalar())
