"""Backfill gnss_interference_zones from gnss_spoofed_positions.

Classification logic (default = jamming):
  - jamming:  DEFAULT for all GNSS anomalies. GPS interference causing
              position errors. This is cheap, common, and covers ~95% of
              real-world GNSS interference. Zones at real vessel positions.
  - spoofing: ONLY when spoofed positions cluster tightly at a target that
              is far (>200km) from the real vessel positions. This means
              vessels were deliberately dragged to a fake location.
              Known hotspots: Kaliningrad, Syria/Lebanon, Iran, Black Sea.

Usage:
    python -m gnss_zone_backfill
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Clustering parameters
SPOOFING_CLUSTER_RADIUS_DEG = 0.2   # ~12nm — spoofing targets cluster tightly
JAMMING_CLUSTER_RADIUS_DEG = 0.5    # ~30nm — jamming zones are broader
MIN_CLUSTER_POINTS = 5
MIN_CLUSTER_VESSELS = 3
ZONE_DURATION_HOURS = 0.75          # 45min per zone
TIME_WINDOW_HOURS = 3
# The key threshold: how far must spoofed positions be from real positions
# to qualify as spoofing (deliberate drag to a remote target)?
MIN_SPOOFING_DISPLACEMENT_KM = 200


async def backfill_zones(session: AsyncSession) -> int:
    """Read gnss_spoofed_positions and create zone polygons."""

    await session.execute(text("DELETE FROM gnss_interference_zones"))
    logger.info("Cleared existing zones")

    # Get time range
    result = await session.execute(text("""
        SELECT MIN(detected_at) AS min_t, MAX(detected_at) AS max_t, COUNT(*) AS cnt
        FROM gnss_spoofed_positions
    """))
    row = result.mappings().first()
    if not row or not row["min_t"]:
        return 0

    min_t, max_t, total = row["min_t"], row["max_t"], row["cnt"]
    logger.info("Processing %d positions from %s to %s", total, min_t, max_t)

    zones_created = 0
    spoofing_zones = 0
    jamming_zones = 0

    window_start = min_t.replace(minute=0, second=0, microsecond=0)
    while window_start < max_t:
        window_end = window_start + timedelta(hours=TIME_WINDOW_HOURS)

        # Step 1: Try to find spoofing targets — tight clusters of spoofed
        # positions that are far from real positions
        n = await _create_spoofing_zones(session, window_start, window_end)
        zones_created += n
        spoofing_zones += n

        # Step 2: Everything else becomes jamming — cluster real positions
        # of ALL anomalous vessels (regardless of bearing)
        n = await _create_jamming_zones(session, window_start, window_end)
        zones_created += n
        jamming_zones += n

        window_start = window_end

    await session.commit()
    logger.info(
        "Backfill complete: %d zones (%d spoofing, %d jamming)",
        zones_created, spoofing_zones, jamming_zones,
    )
    return zones_created


async def _create_spoofing_zones(
    session: AsyncSession,
    window_start: datetime,
    window_end: datetime,
) -> int:
    """Create spoofing zones ONLY where spoofed positions are far from real ones.

    This catches deliberate GPS drag attacks (e.g. vessels near Kaliningrad
    showing positions at airports). The key signal: average distance between
    real and spoofed centroids > 200km.
    """
    result = await session.execute(
        text("""
            WITH pts AS (
                SELECT mmsi, detected_at,
                       spoofed_lat, spoofed_lon,
                       real_lat, real_lon, deviation_km
                FROM gnss_spoofed_positions
                WHERE detected_at >= :ws AND detected_at < :we
                  AND spoofed_lat IS NOT NULL AND spoofed_lon IS NOT NULL
                  AND real_lat IS NOT NULL AND real_lon IS NOT NULL
            ),
            clustered AS (
                SELECT *,
                    ST_ClusterDBSCAN(
                        ST_SetSRID(ST_MakePoint(spoofed_lon, spoofed_lat), 4326),
                        eps := :radius,
                        minpoints := :min_pts
                    ) OVER () AS cluster_id
                FROM pts
            )
            SELECT cluster_id,
                   array_agg(DISTINCT mmsi) AS mmsis,
                   COUNT(*) AS point_count,
                   COUNT(DISTINCT mmsi) AS vessel_count,
                   -- Spoofed centroid (the alleged target)
                   AVG(spoofed_lat) AS spoof_centroid_lat,
                   AVG(spoofed_lon) AS spoof_centroid_lon,
                   -- Real centroid (where vessels actually are)
                   AVG(real_lat) AS real_centroid_lat,
                   AVG(real_lon) AS real_centroid_lon,
                   -- Distance between real and spoofed centroids (in km, approximate)
                   ST_Distance(
                       ST_SetSRID(ST_MakePoint(AVG(spoofed_lon), AVG(spoofed_lat)), 4326)::geography,
                       ST_SetSRID(ST_MakePoint(AVG(real_lon), AVG(real_lat)), 4326)::geography
                   ) / 1000.0 AS displacement_km,
                   MAX(deviation_km) AS max_deviation_km,
                   MIN(detected_at) AS first_seen,
                   MAX(detected_at) AS last_seen,
                   ST_AsText(ST_ConvexHull(
                       ST_Collect(ST_SetSRID(ST_MakePoint(spoofed_lon, spoofed_lat), 4326))
                   )) AS hull_wkt
            FROM clustered
            WHERE cluster_id IS NOT NULL
            GROUP BY cluster_id
            HAVING COUNT(DISTINCT mmsi) >= :min_vessels
            ORDER BY cluster_id
        """),
        {
            "ws": window_start, "we": window_end,
            "radius": SPOOFING_CLUSTER_RADIUS_DEG,
            "min_pts": MIN_CLUSTER_POINTS,
            "min_vessels": MIN_CLUSTER_VESSELS,
        },
    )
    clusters = result.mappings().all()

    zones = 0
    for c in clusters:
        displacement = float(c["displacement_km"] or 0)

        if displacement < MIN_SPOOFING_DISPLACEMENT_KM:
            # Not far enough from real positions — this is jamming/drift, not spoofing
            continue

        logger.info(
            "SPOOFING: target (%.2f, %.2f), real centroid (%.2f, %.2f), "
            "displacement %.0fkm, %d vessels",
            float(c["spoof_centroid_lat"]), float(c["spoof_centroid_lon"]),
            float(c["real_centroid_lat"]), float(c["real_centroid_lon"]),
            displacement, c["vessel_count"],
        )
        zones += await _insert_zone(session, c, "spoofing",
                                     float(c["spoof_centroid_lat"]),
                                     float(c["spoof_centroid_lon"]))
    return zones


async def _create_jamming_zones(
    session: AsyncSession,
    window_start: datetime,
    window_end: datetime,
) -> int:
    """Create jamming zones at real vessel positions.

    ALL anomalous positions become jamming zones (the default). Real
    positions are clustered to show WHERE interference is happening.
    """
    result = await session.execute(
        text("""
            WITH pts AS (
                SELECT mmsi, detected_at, real_lat AS lat, real_lon AS lon, deviation_km
                FROM gnss_spoofed_positions
                WHERE detected_at >= :ws AND detected_at < :we
                  AND real_lat IS NOT NULL AND real_lon IS NOT NULL
            ),
            clustered AS (
                SELECT *,
                    ST_ClusterDBSCAN(
                        ST_SetSRID(ST_MakePoint(lon, lat), 4326),
                        eps := :radius,
                        minpoints := :min_pts
                    ) OVER () AS cluster_id
                FROM pts
            )
            SELECT cluster_id,
                   array_agg(DISTINCT mmsi) AS mmsis,
                   COUNT(*) AS point_count,
                   COUNT(DISTINCT mmsi) AS vessel_count,
                   AVG(lat) AS centroid_lat,
                   AVG(lon) AS centroid_lon,
                   MAX(deviation_km) AS max_deviation_km,
                   MIN(detected_at) AS first_seen,
                   MAX(detected_at) AS last_seen,
                   ST_AsText(ST_ConvexHull(
                       ST_Collect(ST_SetSRID(ST_MakePoint(lon, lat), 4326))
                   )) AS hull_wkt
            FROM clustered
            WHERE cluster_id IS NOT NULL
            GROUP BY cluster_id
            HAVING COUNT(DISTINCT mmsi) >= :min_vessels
            ORDER BY cluster_id
        """),
        {
            "ws": window_start, "we": window_end,
            "radius": JAMMING_CLUSTER_RADIUS_DEG,
            "min_pts": MIN_CLUSTER_POINTS,
            "min_vessels": MIN_CLUSTER_VESSELS,
        },
    )
    clusters = result.mappings().all()

    zones = 0
    for c in clusters:
        zones += await _insert_zone(session, c, "jamming",
                                     float(c["centroid_lat"]),
                                     float(c["centroid_lon"]))
    return zones


async def _insert_zone(
    session: AsyncSession,
    c: Any,
    event_type: str,
    centroid_lat: float,
    centroid_lon: float,
) -> int:
    midpoint = c["first_seen"] + (c["last_seen"] - c["first_seen"]) / 2
    hull_wkt = c["hull_wkt"]

    if hull_wkt.startswith("POINT") or hull_wkt.startswith("LINESTRING"):
        geom_sql = "ST_Buffer(ST_SetSRID(ST_GeomFromText(:hull_wkt), 4326)::geography, 5556)"
    else:
        geom_sql = "ST_Buffer(ST_ConvexHull(ST_SetSRID(ST_GeomFromText(:hull_wkt), 4326))::geography, 1852)"

    severity = "critical" if (c["max_deviation_km"] or 0) > 200 else \
               "high" if (c["max_deviation_km"] or 0) > 100 else \
               "moderate" if (c["max_deviation_km"] or 0) > 50 else "low"

    mmsis = sorted(c["mmsis"])

    await session.execute(
        text(f"""
            INSERT INTO gnss_interference_zones (
                detected_at, expires_at, geometry,
                affected_count, affected_mmsis,
                event_type, peak_severity, details
            ) VALUES (
                :detected_at, :expires_at, {geom_sql},
                :affected_count, :affected_mmsis,
                :event_type, :peak_severity, :details
            )
        """),
        {
            "detected_at": midpoint,
            "expires_at": midpoint + timedelta(hours=ZONE_DURATION_HOURS),
            "hull_wkt": hull_wkt,
            "affected_count": len(mmsis),
            "affected_mmsis": mmsis,
            "event_type": event_type,
            "peak_severity": severity,
            "details": json.dumps({
                "backfilled": True,
                "point_count": c["point_count"],
                "vessel_count": c["vessel_count"],
                "centroid": {"lat": round(centroid_lat, 4), "lon": round(centroid_lon, 4)},
                "max_deviation_km": round(float(c["max_deviation_km"] or 0), 1),
                "displacement_km": round(float(c.get("displacement_km") or 0), 1),
            }),
        },
    )
    return 1


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from shared.db.connection import get_session

    session_factory = get_session()
    async with session_factory() as session:
        zones = await backfill_zones(session)
        logger.info("Backfill complete: %d total zones created", zones)


if __name__ == "__main__":
    asyncio.run(main())
