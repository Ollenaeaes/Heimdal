"""Backfill gnss_interference_zones from gnss_spoofed_positions.

Reclassifies all positions by bearing before creating zones:
  - spoofing: non-cardinal jump where multiple vessels get dragged to the
              SAME target (clustered spoofed positions with spread-out real
              positions confirms it's a spoofing target, not bad data)
  - jamming:  cardinal-direction jumps (within 5° of N/S/E/W) — GPS loss
              causing predictable drift. Zones at the vessel's REAL position.

Interference area is NOT created — it just shows "where ships sail" which
is not useful geographic information.

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
CLUSTER_RADIUS_DEG = 0.25     # ~15nm for spoofing target clusters
JAMMING_CLUSTER_RADIUS_DEG = 0.5  # ~30nm for jamming clusters
MIN_CLUSTER_POINTS = 5
ZONE_DURATION_HOURS = 0.75    # 45min per zone
TIME_WINDOW_HOURS = 3
CARDINAL_THRESHOLD_DEG = 5    # Max deviation from N/S/E/W to classify as jamming
MIN_REAL_SPREAD_KM = 50       # Real positions must be spread >50km to confirm spoofing


async def backfill_zones(session: AsyncSession) -> int:
    """Read gnss_spoofed_positions and create zone polygons."""

    await session.execute(text("DELETE FROM gnss_interference_zones"))
    logger.info("Cleared existing zones")

    # First: reclassify all positions by bearing
    await session.execute(text("""
        UPDATE gnss_spoofed_positions
        SET event_type = CASE
            WHEN real_lat IS NOT NULL AND real_lon IS NOT NULL
                 AND ABS(
                     DEGREES(ATAN2(spoofed_lon - real_lon, spoofed_lat - real_lat))
                     - ROUND(DEGREES(ATAN2(spoofed_lon - real_lon, spoofed_lat - real_lat)) / 90.0) * 90
                 ) < :threshold
            THEN 'jamming'
            ELSE 'spoofing'
        END
    """), {"threshold": CARDINAL_THRESHOLD_DEG})
    await session.commit()

    # Count after reclassification
    result = await session.execute(text("""
        SELECT event_type, COUNT(*) FROM gnss_spoofed_positions GROUP BY event_type
    """))
    for r in result.mappings().all():
        logger.info("  %s: %d positions", r["event_type"], r["count"])

    # Get time range
    result = await session.execute(text("""
        SELECT MIN(detected_at) AS min_t, MAX(detected_at) AS max_t
        FROM gnss_spoofed_positions
    """))
    row = result.mappings().first()
    if not row or not row["min_t"]:
        return 0

    min_t = row["min_t"]
    max_t = row["max_t"]
    zones_created = 0

    window_start = min_t.replace(minute=0, second=0, microsecond=0)
    while window_start < max_t:
        window_end = window_start + timedelta(hours=TIME_WINDOW_HOURS)

        # --- Spoofing targets (red): cluster spoofed positions, verify spread ---
        n = await _create_spoofing_zones(session, window_start, window_end)
        zones_created += n

        # --- Jamming zones (purple): cluster real positions of jamming victims ---
        n = await _create_jamming_zones(session, window_start, window_end)
        zones_created += n

        window_start = window_end

    await session.commit()
    logger.info("Backfill complete: %d zones created", zones_created)
    return zones_created


async def _create_spoofing_zones(
    session: AsyncSession,
    window_start: datetime,
    window_end: datetime,
) -> int:
    """Create spoofing target zones.

    Clusters spoofed positions (where GPS says vessels are). Only keeps
    clusters where the real positions are geographically spread out — this
    confirms multiple vessels from different locations were dragged to the
    same target (real spoofing), vs vessels just being in the same area
    with bad data.
    """
    result = await session.execute(
        text("""
            WITH pts AS (
                SELECT mmsi, detected_at, spoofed_lat AS lat, spoofed_lon AS lon,
                       real_lat, real_lon, deviation_km
                FROM gnss_spoofed_positions
                WHERE detected_at >= :ws AND detected_at < :we
                  AND event_type = 'spoofing'
                  AND spoofed_lat IS NOT NULL AND spoofed_lon IS NOT NULL
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
                   )) AS hull_wkt,
                   -- Measure spread of real positions to confirm spoofing
                   CASE WHEN COUNT(*) FILTER (WHERE real_lat IS NOT NULL) >= 2
                        THEN ST_MaxDistance(
                            ST_Collect(ST_SetSRID(ST_MakePoint(real_lon, real_lat), 4326))
                                FILTER (WHERE real_lat IS NOT NULL),
                            ST_Collect(ST_SetSRID(ST_MakePoint(real_lon, real_lat), 4326))
                                FILTER (WHERE real_lat IS NOT NULL)
                        ) * 111  -- rough deg-to-km
                        ELSE 0
                   END AS real_spread_km
            FROM clustered
            WHERE cluster_id IS NOT NULL
            GROUP BY cluster_id
            HAVING COUNT(DISTINCT mmsi) >= 3
            ORDER BY cluster_id
        """),
        {"ws": window_start, "we": window_end,
         "radius": CLUSTER_RADIUS_DEG, "min_pts": MIN_CLUSTER_POINTS},
    )
    clusters = result.mappings().all()

    zones = 0
    for c in clusters:
        # Only create zone if real positions are spread out (confirms spoofing)
        if (c["real_spread_km"] or 0) < MIN_REAL_SPREAD_KM:
            logger.debug(
                "Skipping cluster near (%.2f, %.2f): real spread only %.0fkm (need %dkm)",
                float(c["centroid_lat"]), float(c["centroid_lon"]),
                float(c["real_spread_km"] or 0), MIN_REAL_SPREAD_KM,
            )
            continue

        zones += await _insert_zone(session, c, "spoofing")
    return zones


async def _create_jamming_zones(
    session: AsyncSession,
    window_start: datetime,
    window_end: datetime,
) -> int:
    """Create jamming zones at real vessel positions (where jamming occurs)."""
    result = await session.execute(
        text("""
            WITH pts AS (
                SELECT mmsi, detected_at, real_lat AS lat, real_lon AS lon, deviation_km
                FROM gnss_spoofed_positions
                WHERE detected_at >= :ws AND detected_at < :we
                  AND event_type = 'jamming'
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
            HAVING COUNT(DISTINCT mmsi) >= 3
            ORDER BY cluster_id
        """),
        {"ws": window_start, "we": window_end,
         "radius": JAMMING_CLUSTER_RADIUS_DEG, "min_pts": MIN_CLUSTER_POINTS},
    )
    clusters = result.mappings().all()

    zones = 0
    for c in clusters:
        zones += await _insert_zone(session, c, "jamming")
    return zones


async def _insert_zone(
    session: AsyncSession,
    c: Any,
    event_type: str,
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
                "centroid": {
                    "lat": round(float(c["centroid_lat"]), 4),
                    "lon": round(float(c["centroid_lon"]), 4),
                },
                "max_deviation_km": round(float(c["max_deviation_km"] or 0), 1),
                "real_spread_km": round(float(c.get("real_spread_km") or 0), 1),
            }),
        },
    )
    logger.info(
        "Created %s zone near (%.2f, %.2f): %d vessels, %d points",
        event_type, float(c["centroid_lat"]), float(c["centroid_lon"]),
        c["vessel_count"], c["point_count"],
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
