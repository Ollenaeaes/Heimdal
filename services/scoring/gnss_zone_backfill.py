"""Backfill gnss_interference_zones from gnss_spoofed_positions.

Reads the 43k+ rows in gnss_spoofed_positions (from the retrospective
detector) and creates polygon zones using DBSCAN clustering + convex hull.

Three zone types are created:
  - spoofing:          cluster of spoofed_lat/spoofed_lon (where GPS says vessels are)
  - interference_area: cluster of real_lat/real_lon (where vessels actually were)
  - jamming:           positions with event_type='jamming'

Usage:
    python -m gnss_zone_backfill          # runs against the database
    docker compose exec scoring python -m gnss_zone_backfill
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
CLUSTER_RADIUS_DEG = 0.25     # ~15nm for spoofing target clusters (tight)
CLUSTER_RADIUS_WIDE_DEG = 0.5 # ~30nm for interference area / jamming clusters
MIN_CLUSTER_POINTS = 5        # Minimum points per cluster
ZONE_DURATION_HOURS = 1.5     # Each zone lasts 1.5h from its midpoint time
TIME_WINDOW_HOURS = 3         # Group positions into 3-hour windows


async def backfill_zones(session: AsyncSession) -> int:
    """Read gnss_spoofed_positions and create zone polygons."""

    # Clear existing zones (they're all stale from failed iterations)
    await session.execute(text("DELETE FROM gnss_interference_zones"))
    logger.info("Cleared existing zones")

    # Get time range of data
    result = await session.execute(text("""
        SELECT MIN(detected_at) AS min_t, MAX(detected_at) AS max_t, COUNT(*) AS cnt
        FROM gnss_spoofed_positions
    """))
    row = result.mappings().first()
    if not row or not row["min_t"]:
        logger.info("No spoofed positions found")
        return 0

    min_t = row["min_t"]
    max_t = row["max_t"]
    total = row["cnt"]
    logger.info("Found %d spoofed positions from %s to %s", total, min_t, max_t)

    zones_created = 0

    # Process in 6-hour windows to create time-scoped zones
    window_start = min_t.replace(minute=0, second=0, microsecond=0)
    while window_start < max_t:
        window_end = window_start + timedelta(hours=TIME_WINDOW_HOURS)

        # --- Spoofing target zones (red): cluster spoofed positions ---
        n = await _create_zones_from_positions(
            session, window_start, window_end,
            lat_col="spoofed_lat", lon_col="spoofed_lon",
            event_type_filter=None,  # all types for spoofed positions
            zone_event_type="spoofing",
            cluster_radius=CLUSTER_RADIUS_DEG,
        )
        zones_created += n

        # --- Interference area zones (cyan): cluster real positions of spoofing victims ---
        n = await _create_zones_from_positions(
            session, window_start, window_end,
            lat_col="real_lat", lon_col="real_lon",
            event_type_filter="spoofing",
            zone_event_type="interference_area",
            cluster_radius=CLUSTER_RADIUS_WIDE_DEG,
        )
        zones_created += n

        # --- Jamming zones (purple): cluster real positions of jamming victims ---
        n = await _create_zones_from_positions(
            session, window_start, window_end,
            lat_col="real_lat", lon_col="real_lon",
            event_type_filter="jamming",
            zone_event_type="jamming",
            cluster_radius=CLUSTER_RADIUS_WIDE_DEG,
        )
        zones_created += n

        window_start = window_end

    await session.commit()
    logger.info("Backfill complete: %d zones created", zones_created)
    return zones_created


async def _create_zones_from_positions(
    session: AsyncSession,
    window_start: datetime,
    window_end: datetime,
    lat_col: str,
    lon_col: str,
    event_type_filter: str | None,
    zone_event_type: str,
    cluster_radius: float,
) -> int:
    """Cluster positions in a time window and create zone polygons."""

    # Build the query to get positions
    where_parts = [
        "detected_at >= :ws",
        "detected_at < :we",
        f"{lat_col} IS NOT NULL",
        f"{lon_col} IS NOT NULL",
    ]
    params: dict[str, Any] = {"ws": window_start, "we": window_end}

    if event_type_filter:
        where_parts.append("event_type = :evt")
        params["evt"] = event_type_filter

    where_sql = " AND ".join(where_parts)

    # Use DBSCAN clustering in PostGIS
    result = await session.execute(
        text(f"""
            WITH pts AS (
                SELECT mmsi, detected_at, {lat_col} AS lat, {lon_col} AS lon, deviation_km
                FROM gnss_spoofed_positions
                WHERE {where_sql}
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
                   ST_AsText(
                       ST_ConvexHull(
                           ST_Collect(ST_SetSRID(ST_MakePoint(lon, lat), 4326))
                       )
                   ) AS hull_wkt
            FROM clustered
            WHERE cluster_id IS NOT NULL
            GROUP BY cluster_id
            HAVING COUNT(DISTINCT mmsi) >= 3
            ORDER BY cluster_id
        """),
        {**params, "radius": cluster_radius, "min_pts": MIN_CLUSTER_POINTS},
    )
    clusters = result.mappings().all()

    if not clusters:
        return 0

    zones_created = 0
    for c in clusters:
        midpoint = c["first_seen"] + (c["last_seen"] - c["first_seen"]) / 2
        hull_wkt = c["hull_wkt"]

        # For single points or collinear points, the convex hull is a point/line.
        # Buffer it to create a visible polygon.
        if hull_wkt.startswith("POINT") or hull_wkt.startswith("LINESTRING"):
            geom_sql = f"""ST_Buffer(
                ST_SetSRID(ST_GeomFromText(:hull_wkt), 4326)::geography,
                5556
            )"""  # 3nm buffer for point/line hulls
        else:
            # For actual polygons, apply minimal buffer for smoothness
            geom_sql = f"""ST_Buffer(
                ST_ConvexHull(ST_SetSRID(ST_GeomFromText(:hull_wkt), 4326))::geography,
                1852
            )"""  # 1nm buffer

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
                    :detected_at,
                    :expires_at,
                    {geom_sql},
                    :affected_count,
                    :affected_mmsis,
                    :event_type,
                    :peak_severity,
                    :details
                )
            """),
            {
                "detected_at": midpoint,
                "expires_at": midpoint + timedelta(hours=ZONE_DURATION_HOURS),
                "hull_wkt": hull_wkt,
                "affected_count": len(mmsis),
                "affected_mmsis": mmsis,
                "event_type": zone_event_type,
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
                    "time_range": {
                        "start": c["first_seen"].isoformat(),
                        "end": c["last_seen"].isoformat(),
                    },
                }),
            },
        )
        zones_created += 1
        logger.info(
            "Created %s zone near (%.2f, %.2f): %d vessels, %d points",
            zone_event_type, float(c["centroid_lat"]), float(c["centroid_lon"]),
            c["vessel_count"], c["point_count"],
        )

    return zones_created


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
