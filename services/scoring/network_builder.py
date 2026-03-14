"""Network edge builder for sanctions evasion network mapping.

Creates ENCOUNTER, PROXIMITY, and OWNERSHIP edges between vessels
based on GFW events, loitering proximity, and shared ownership data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.network_repository import upsert_network_edge

logger = logging.getLogger("scoring.network_builder")


async def create_encounter_edge(
    session: AsyncSession,
    mmsi_a: int,
    mmsi_b: int,
    location_lat: float,
    location_lon: float,
    observed_at: datetime,
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Create an ENCOUNTER edge from a GFW encounter event.

    Handles missing vessel profiles gracefully by logging a warning
    and skipping the edge creation.
    """
    # Verify both vessels exist in vessel_profiles
    for mmsi in (mmsi_a, mmsi_b):
        result = await session.execute(
            text("SELECT 1 FROM vessel_profiles WHERE mmsi = :mmsi"),
            {"mmsi": mmsi},
        )
        if result.first() is None:
            logger.warning(
                "skipping_encounter_edge_missing_profile",
                extra={"mmsi": mmsi, "mmsi_a": mmsi_a, "mmsi_b": mmsi_b},
            )
            return

    await upsert_network_edge(
        session,
        mmsi_a=mmsi_a,
        mmsi_b=mmsi_b,
        edge_type="encounter",
        confidence=1.0,
        location={"lat": location_lat, "lon": location_lon},
        details=details or {"observed_at": observed_at.isoformat()},
    )
    logger.info(
        "encounter_edge_created",
        extra={"mmsi_a": mmsi_a, "mmsi_b": mmsi_b},
    )


async def create_proximity_edges(
    session: AsyncSession,
    mmsi: int,
    lat: float,
    lon: float,
    observed_at: datetime,
) -> int:
    """Create PROXIMITY edges from STS zone loitering co-occurrence.

    Queries GFW loitering events in the same STS zone within +/-24 hours.
    Creates PROXIMITY edges between all pairs with confidence=0.7.
    Only applies to STS zone loitering (not open ocean).

    Returns the number of edges created.
    """
    from services.scoring.rules.zone_helpers import is_in_sts_zone

    # Check if the location is in an STS zone
    zone_name = await is_in_sts_zone(session, lat, lon)
    if zone_name is None:
        return 0

    # Verify the queried vessel exists
    result = await session.execute(
        text("SELECT 1 FROM vessel_profiles WHERE mmsi = :mmsi"),
        {"mmsi": mmsi},
    )
    if result.first() is None:
        logger.warning(
            "skipping_proximity_edges_missing_profile",
            extra={"mmsi": mmsi},
        )
        return 0

    # Find other vessels loitering in the same area within +/-24 hours
    time_start = observed_at - timedelta(hours=24)
    time_end = observed_at + timedelta(hours=24)

    result = await session.execute(
        text("""
            SELECT DISTINCT mmsi FROM gfw_events
            WHERE event_type = 'loitering'
              AND mmsi != :mmsi
              AND start_time BETWEEN :time_start AND :time_end
              AND mmsi IN (SELECT mmsi FROM vessel_profiles)
        """),
        {"mmsi": mmsi, "time_start": time_start, "time_end": time_end},
    )
    nearby_mmsis = [row[0] for row in result.all()]

    # Filter to only those in the same STS zone
    edges_created = 0
    for other_mmsi in nearby_mmsis:
        # Get the other vessel's loitering position
        pos_result = await session.execute(
            text("""
                SELECT lat, lon FROM gfw_events
                WHERE event_type = 'loitering'
                  AND mmsi = :other_mmsi
                  AND start_time BETWEEN :time_start AND :time_end
                ORDER BY start_time DESC
                LIMIT 1
            """),
            {"other_mmsi": other_mmsi, "time_start": time_start, "time_end": time_end},
        )
        pos_row = pos_result.first()
        if pos_row is None:
            continue

        other_lat, other_lon = pos_row[0], pos_row[1]
        other_zone = await is_in_sts_zone(session, other_lat, other_lon)
        if other_zone != zone_name:
            continue

        await upsert_network_edge(
            session,
            mmsi_a=mmsi,
            mmsi_b=other_mmsi,
            edge_type="proximity",
            confidence=0.7,
            location={"lat": lat, "lon": lon},
            details={
                "zone": zone_name,
                "observed_at": observed_at.isoformat(),
            },
        )
        edges_created += 1

    if edges_created:
        logger.info(
            "proximity_edges_created",
            extra={"mmsi": mmsi, "count": edges_created, "zone": zone_name},
        )
    return edges_created


async def create_ownership_edges(
    session: AsyncSession,
    mmsi: int,
) -> int:
    """Create OWNERSHIP edges based on shared registered_owner or commercial_manager.

    Queries vessel_profiles for matching ownership data (case-insensitive).
    Creates OWNERSHIP edges with confidence=1.0 and location=NULL.

    Returns the number of edges created.
    """
    # Get the vessel's ownership data
    result = await session.execute(
        text("""
            SELECT registered_owner, ownership_data
            FROM vessel_profiles
            WHERE mmsi = :mmsi
        """),
        {"mmsi": mmsi},
    )
    row = result.mappings().first()
    if row is None:
        logger.warning(
            "skipping_ownership_edges_missing_profile",
            extra={"mmsi": mmsi},
        )
        return 0

    registered_owner = row.get("registered_owner")
    ownership_data = row.get("ownership_data") or {}

    # Extract commercial_manager from ownership_data JSONB
    commercial_manager = None
    if isinstance(ownership_data, dict):
        commercial_manager = ownership_data.get("commercial_manager")

    if not registered_owner and not commercial_manager:
        return 0

    edges_created = 0

    # Find vessels with matching registered_owner (case-insensitive)
    if registered_owner:
        result = await session.execute(
            text("""
                SELECT mmsi FROM vessel_profiles
                WHERE mmsi != :mmsi
                  AND LOWER(registered_owner) = LOWER(:registered_owner)
            """),
            {"mmsi": mmsi, "registered_owner": registered_owner},
        )
        for matched_row in result.all():
            other_mmsi = matched_row[0]
            await upsert_network_edge(
                session,
                mmsi_a=mmsi,
                mmsi_b=other_mmsi,
                edge_type="ownership",
                confidence=1.0,
                location=None,
                details={"match_field": "registered_owner", "value": registered_owner},
            )
            edges_created += 1

    # Find vessels with matching commercial_manager (case-insensitive)
    if commercial_manager:
        result = await session.execute(
            text("""
                SELECT mmsi FROM vessel_profiles
                WHERE mmsi != :mmsi
                  AND LOWER(ownership_data->>'commercial_manager') = LOWER(:commercial_manager)
            """),
            {"mmsi": mmsi, "commercial_manager": commercial_manager},
        )
        for matched_row in result.all():
            other_mmsi = matched_row[0]
            await upsert_network_edge(
                session,
                mmsi_a=mmsi,
                mmsi_b=other_mmsi,
                edge_type="ownership",
                confidence=1.0,
                location=None,
                details={"match_field": "commercial_manager", "value": commercial_manager},
            )
            edges_created += 1

    if edges_created:
        logger.info(
            "ownership_edges_created",
            extra={"mmsi": mmsi, "count": edges_created},
        )
    return edges_created
