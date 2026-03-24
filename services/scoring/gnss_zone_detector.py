"""Area-Based GNSS Interference Zone Detector.

Standalone detector that identifies GNSS interference zones by correlating
anomalous position data across multiple vessels in the same area and time
window.  Runs periodically (cron or called from the scoring engine).

Algorithm
---------
1. Query recent positions (last LOOKBACK_MINUTES) from vessel_positions.
2. For each vessel with 2+ positions, compute implied speed between
   consecutive pairs.
3. Flag position pairs where implied speed exceeds SPEED_THRESHOLD_KN.
4. Cluster anomalous positions with PostGIS ST_ClusterDBSCAN (eps =
   CLUSTER_RADIUS_DEG, minPoints = MIN_CLUSTER_VESSELS).
5. For each cluster with 3+ distinct MMSIs:
   - If an active zone overlaps (geometry intersection + within 24 h):
     update it (merge MMSIs, push expires_at forward).
   - Otherwise create a new zone (convex hull buffered by BUFFER_M).
6. Classify as 'spoofing' (positions present but displaced) vs 'jamming'
   (AIS gap in the area).
7. Tag affected vessels in vessel_profiles.gnss_affected.
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_CLUSTER_VESSELS = 3       # Minimum distinct MMSIs per zone
SPEED_THRESHOLD_KN = 45       # Implied speed threshold (knots)
CLUSTER_RADIUS_DEG = 0.25     # ~15 nautical miles in degrees at mid-latitudes
BUFFER_M = 9_260              # 5 nautical miles in metres
ZONE_EXPIRY_HOURS = 24        # How long a zone stays active
LOOKBACK_MINUTES = 60         # How far back to scan positions

# Speed of light sanity constant: metres-per-second for 1 knot
_KNOTS_TO_MPS = 0.514444


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def detect_gnss_zones(session: AsyncSession) -> int:
    """Run the full detection pipeline and return the number of zones
    created or updated.

    Parameters
    ----------
    session:
        An active SQLAlchemy async session (from ``get_session()()``).

    Returns
    -------
    Number of zones created or refreshed.
    """
    anomalous = await _find_anomalous_positions(session)
    if not anomalous:
        logger.info("No anomalous positions found in the last %d minutes", LOOKBACK_MINUTES)
        return 0

    clusters = await _cluster_anomalous_positions(session, anomalous)
    if not clusters:
        logger.info("No spatial clusters with >= %d vessels", MIN_CLUSTER_VESSELS)
        return 0

    zones_affected = 0
    for cluster in clusters:
        zones_affected += await _upsert_zone(session, cluster)

    # Commit zones first so they're visible even if tagging is slow/fails
    await session.commit()

    try:
        await _tag_affected_vessels(session)
        await session.commit()
    except Exception:
        logger.warning("Failed to tag affected vessels, zones were still committed", exc_info=True)
        await session.rollback()

    logger.info("GNSS zone detection complete: %d zones created/updated", zones_affected)
    return zones_affected


# ---------------------------------------------------------------------------
# Step 1 & 2 & 3: Find anomalous positions (implied speed > threshold)
# ---------------------------------------------------------------------------


async def _find_anomalous_positions(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Return positions whose implied speed from their predecessor exceeds
    the threshold.

    For each anomalous pair, emits TWO rows:
    - The post-jump (spoofed) position with position_type='spoofed'
    - The pre-jump (real) position with position_type='pre_jump'

    This allows DBSCAN to cluster both the spoofing target area AND the
    real interference footprint separately.

    Each row contains: mmsi, lat, lon, timestamp, implied_speed_kn,
    position_wkt, position_type.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES)

    # Use a window function to pair consecutive positions per vessel and
    # compute implied speed via ST_Distance on geography (returns metres).
    # Returns both the post-jump AND pre-jump positions.
    result = await session.execute(
        text("""
            WITH ordered AS (
                SELECT
                    mmsi,
                    "timestamp",
                    position,
                    ST_Y(position::geometry) AS lat,
                    ST_X(position::geometry) AS lon,
                    LAG(position)   OVER w AS prev_position,
                    LAG("timestamp") OVER w AS prev_timestamp,
                    ST_Y(LAG(position) OVER w ::geometry) AS prev_lat,
                    ST_X(LAG(position) OVER w ::geometry) AS prev_lon
                FROM vessel_positions
                WHERE "timestamp" >= :cutoff
                WINDOW w AS (PARTITION BY mmsi ORDER BY "timestamp")
            ),
            with_speed AS (
                SELECT
                    mmsi,
                    "timestamp",
                    position,
                    lat,
                    lon,
                    prev_lat,
                    prev_lon,
                    prev_timestamp,
                    prev_position,
                    CASE
                        WHEN prev_position IS NOT NULL
                             AND EXTRACT(EPOCH FROM ("timestamp" - prev_timestamp)) > 0
                        THEN (
                            ST_Distance(position, prev_position)
                            / EXTRACT(EPOCH FROM ("timestamp" - prev_timestamp))
                            / :knots_to_mps
                        )
                        ELSE NULL
                    END AS implied_speed_kn
                FROM ordered
                WHERE prev_position IS NOT NULL
            )
            SELECT
                mmsi,
                "timestamp",
                lat,
                lon,
                prev_lat,
                prev_lon,
                prev_timestamp,
                implied_speed_kn,
                ST_AsText(position::geometry) AS position_wkt,
                ST_AsText(prev_position::geometry) AS prev_position_wkt
            FROM with_speed
            WHERE implied_speed_kn > :speed_threshold
            ORDER BY "timestamp"
        """),
        {
            "cutoff": cutoff,
            "knots_to_mps": _KNOTS_TO_MPS,
            "speed_threshold": SPEED_THRESHOLD_KN,
        },
    )
    rows = result.mappings().all()

    logger.info(
        "Found %d anomalous position pairs (implied speed > %d kn) in the last %d min",
        len(rows), SPEED_THRESHOLD_KN, LOOKBACK_MINUTES,
    )

    # Emit both post-jump (spoofed) and pre-jump (real) positions
    positions: list[dict[str, Any]] = []
    for r in rows:
        row = dict(r)
        # Post-jump position (where GPS says the vessel jumped to)
        positions.append({
            "mmsi": row["mmsi"],
            "lat": row["lat"],
            "lon": row["lon"],
            "timestamp": row["timestamp"],
            "implied_speed_kn": row["implied_speed_kn"],
            "position_wkt": row["position_wkt"],
            "position_type": "spoofed",
        })
        # Pre-jump position (where the vessel actually was)
        if row.get("prev_lat") is not None and row.get("prev_lon") is not None:
            positions.append({
                "mmsi": row["mmsi"],
                "lat": row["prev_lat"],
                "lon": row["prev_lon"],
                "timestamp": row["prev_timestamp"],
                "implied_speed_kn": row["implied_speed_kn"],
                "position_wkt": row["prev_position_wkt"],
                "position_type": "pre_jump",
            })

    logger.info(
        "Emitted %d positions (%d spoofed + %d pre-jump) for clustering",
        len(positions),
        sum(1 for p in positions if p["position_type"] == "spoofed"),
        sum(1 for p in positions if p["position_type"] == "pre_jump"),
    )
    return positions


# ---------------------------------------------------------------------------
# Step 4: Cluster anomalous positions with ST_ClusterDBSCAN
# ---------------------------------------------------------------------------


async def _cluster_anomalous_positions(
    session: AsyncSession,
    anomalous: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Cluster anomalous positions using PostGIS ST_ClusterDBSCAN.

    Returns a list of clusters, each being a list of position dicts.
    Only clusters with >= MIN_CLUSTER_VESSELS distinct MMSIs are returned.
    """
    if not anomalous:
        return []

    # Build a VALUES clause for the anomalous positions so we can feed them
    # into ST_ClusterDBSCAN inside the database.
    values_parts: list[str] = []
    params: dict[str, Any] = {
        "cluster_radius": CLUSTER_RADIUS_DEG,
        "min_pts": MIN_CLUSTER_VESSELS,
    }
    for i, row in enumerate(anomalous):
        values_parts.append(
            f"(CAST(:mmsi_{i} AS int), CAST(:lat_{i} AS float8), CAST(:lon_{i} AS float8), "
            f"CAST(:ts_{i} AS timestamptz), CAST(:speed_{i} AS float8), CAST(:ptype_{i} AS text))"
        )
        params[f"mmsi_{i}"] = row["mmsi"]
        params[f"lat_{i}"] = float(row["lat"])
        params[f"lon_{i}"] = float(row["lon"])
        params[f"ts_{i}"] = row["timestamp"]
        params[f"speed_{i}"] = float(row["implied_speed_kn"])
        params[f"ptype_{i}"] = row.get("position_type", "spoofed")

    values_sql = ",\n".join(values_parts)

    result = await session.execute(
        text(f"""
            WITH anomalous(mmsi, lat, lon, ts, implied_speed_kn, position_type) AS (
                VALUES {values_sql}
            ),
            clustered AS (
                SELECT
                    mmsi,
                    lat,
                    lon,
                    ts,
                    implied_speed_kn,
                    position_type,
                    ST_ClusterDBSCAN(
                        ST_SetSRID(ST_MakePoint(lon, lat), 4326),
                        eps := :cluster_radius,
                        minpoints := :min_pts
                    ) OVER () AS cluster_id
                FROM anomalous
            )
            SELECT
                cluster_id,
                mmsi,
                lat,
                lon,
                ts,
                implied_speed_kn,
                position_type
            FROM clustered
            WHERE cluster_id IS NOT NULL
            ORDER BY cluster_id, ts
        """),
        params,
    )
    rows = result.mappings().all()

    # Group by cluster_id
    clusters_map: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        cid = r["cluster_id"]
        clusters_map.setdefault(cid, []).append(dict(r))

    # Filter: keep only clusters with enough distinct vessels
    valid_clusters: list[list[dict[str, Any]]] = []
    for cid, members in clusters_map.items():
        distinct_mmsis = {m["mmsi"] for m in members}
        if len(distinct_mmsis) >= MIN_CLUSTER_VESSELS:
            valid_clusters.append(members)
            logger.info(
                "Cluster %d: %d positions from %d distinct vessels",
                cid, len(members), len(distinct_mmsis),
            )
        else:
            logger.debug(
                "Cluster %d dropped: only %d distinct vessels (need %d)",
                cid, len(distinct_mmsis), MIN_CLUSTER_VESSELS,
            )

    return valid_clusters


# ---------------------------------------------------------------------------
# Step 5 & 6: Create or update zones
# ---------------------------------------------------------------------------


async def _upsert_zone(
    session: AsyncSession,
    cluster: list[dict[str, Any]],
) -> int:
    """Create a new GNSS interference zone or update an existing one.

    Returns 1 if a zone was created/updated, 0 otherwise.
    """
    now = datetime.now(timezone.utc)
    mmsis = sorted({m["mmsi"] for m in cluster})
    centroid_lat = sum(m["lat"] for m in cluster) / len(cluster)
    centroid_lon = sum(m["lon"] for m in cluster) / len(cluster)

    # Classify event type: spoofing (positions present but anomalous) vs
    # jamming (would need AIS gap analysis — for now default to spoofing
    # since we detected anomalous positions, not gaps).
    event_type = _classify_event_type(cluster)

    # Determine peak severity from implied speed
    peak_speed = max(m["implied_speed_kn"] for m in cluster)
    peak_severity = _severity_from_speed(peak_speed)

    # Check for existing active zone that overlaps spatially and temporally
    existing = await session.execute(
        text("""
            SELECT id, affected_mmsis, affected_count
            FROM gnss_interference_zones
            WHERE expires_at > :now
              AND detected_at > :min_time
              AND ST_DWithin(
                    geometry,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    :buffer
              )
            ORDER BY detected_at DESC
            LIMIT 1
        """),
        {
            "now": now,
            "min_time": now - timedelta(hours=ZONE_EXPIRY_HOURS),
            "lat": centroid_lat,
            "lon": centroid_lon,
            "buffer": 27780,  # 15nm in meters for ST_DWithin geography
        },
    )
    row = existing.mappings().first()

    if row:
        # Update existing zone: merge MMSIs, push expiry forward
        zone_id = row["id"]
        existing_mmsis = list(row["affected_mmsis"] or [])
        merged_mmsis = sorted(set(existing_mmsis) | set(mmsis))

        await session.execute(
            text("""
                UPDATE gnss_interference_zones
                SET expires_at      = :expires_at,
                    affected_count  = :affected_count,
                    affected_mmsis  = :affected_mmsis,
                    event_type      = :event_type,
                    peak_severity   = :peak_severity,
                    details         = details || CAST(:new_details AS jsonb)
                WHERE id = :zone_id
            """),
            {
                "zone_id": zone_id,
                "expires_at": now + timedelta(hours=ZONE_EXPIRY_HOURS),
                "affected_count": len(merged_mmsis),
                "affected_mmsis": merged_mmsis,
                "event_type": event_type,
                "peak_severity": peak_severity,
                "new_details": json.dumps({
                    "refreshed_at": now.isoformat(),
                    "new_positions": len(cluster),
                    "new_mmsis": mmsis,
                    "peak_implied_speed_kn": round(peak_speed, 1),
                }),
            },
        )
        logger.info(
            "Updated GNSS zone %d: %d vessels (was %d), type=%s, severity=%s",
            zone_id, len(merged_mmsis), len(existing_mmsis), event_type, peak_severity,
        )
        return 1

    # Build new zone geometry: convex hull of cluster positions buffered by 5nm
    points_sql = ", ".join(
        f"ST_SetSRID(ST_MakePoint({m['lon']}, {m['lat']}), 4326)"
        for m in cluster
    )

    await session.execute(
        text(f"""
            INSERT INTO gnss_interference_zones (
                detected_at, expires_at, geometry,
                affected_count, affected_mmsis,
                event_type, peak_severity,
                details
            ) VALUES (
                :detected_at,
                :expires_at,
                ST_Buffer(
                    ST_ConvexHull(ST_Collect(ARRAY[{points_sql}])),
                    :buffer_m
                )::geography,
                :affected_count,
                :affected_mmsis,
                :event_type,
                :peak_severity,
                :details
            )
        """),
        {
            "detected_at": now,
            "expires_at": now + timedelta(hours=ZONE_EXPIRY_HOURS),
            "buffer_m": BUFFER_M,
            "affected_count": len(mmsis),
            "affected_mmsis": mmsis,
            "event_type": event_type,
            "peak_severity": peak_severity,
            "details": json.dumps({
                "created_at": now.isoformat(),
                "position_count": len(cluster),
                "mmsis": mmsis,
                "peak_implied_speed_kn": round(peak_speed, 1),
                "centroid": {"lat": round(centroid_lat, 4), "lon": round(centroid_lon, 4)},
            }),
        },
    )
    logger.info(
        "Created new GNSS zone near (%.4f, %.4f): %d vessels, type=%s, severity=%s",
        centroid_lat, centroid_lon, len(mmsis), event_type, peak_severity,
    )
    return 1


def _classify_event_type(cluster: list[dict[str, Any]]) -> str:
    """Classify a cluster by its dominant position type.

    - 'interference_area': majority of positions are pre-jump (where vessels
      actually were when their GPS was spoofed)
    - 'spoofing': majority of positions are spoofed (where GPS dragged them to)
    - 'jamming': reserved for future AIS gap-based detection
    """
    pre_jump_count = sum(1 for m in cluster if m.get("position_type") == "pre_jump")
    total = len(cluster)
    if total > 0 and pre_jump_count > total / 2:
        return "interference_area"
    return "spoofing"


def _severity_from_speed(peak_speed_kn: float) -> str:
    """Map peak implied speed to a severity level."""
    if peak_speed_kn > 200:
        return "critical"
    elif peak_speed_kn > 100:
        return "high"
    elif peak_speed_kn > 60:
        return "moderate"
    return "low"


# ---------------------------------------------------------------------------
# Step 7: Tag affected vessels
# ---------------------------------------------------------------------------


async def _tag_affected_vessels(session: AsyncSession) -> None:
    """Update vessel_profiles.gnss_affected for vessels in active zones."""
    now = datetime.now(timezone.utc)

    # Clear stale tags (zones that have expired)
    await session.execute(
        text("""
            UPDATE vessel_profiles
            SET gnss_affected = NULL
            WHERE gnss_affected IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM gnss_interference_zones
                  WHERE expires_at > :now
                    AND mmsi = ANY(affected_mmsis)
                    AND vessel_profiles.mmsi = mmsi
              )
        """),
        {"now": now},
    )

    # Tag vessels that are in active zones
    result = await session.execute(
        text("""
            SELECT
                id AS zone_id,
                affected_mmsis,
                event_type,
                peak_severity,
                detected_at,
                expires_at
            FROM gnss_interference_zones
            WHERE expires_at > :now
        """),
        {"now": now},
    )
    active_zones = result.mappings().all()

    for zone in active_zones:
        zone_info = json.dumps({
            "zone_id": zone["zone_id"],
            "event_type": zone["event_type"],
            "severity": zone["peak_severity"],
            "detected_at": zone["detected_at"].isoformat() if zone["detected_at"] else None,
            "expires_at": zone["expires_at"].isoformat() if zone["expires_at"] else None,
        })

        mmsi_list = list(zone["affected_mmsis"] or [])
        if not mmsi_list:
            continue

        await session.execute(
            text("""
                UPDATE vessel_profiles
                SET gnss_affected = CAST(:zone_info AS jsonb)
                WHERE mmsi = ANY(:mmsis)
            """),
            {
                "zone_info": zone_info,
                "mmsis": mmsi_list,
            },
        )

    logger.info(
        "Tagged vessels for %d active GNSS interference zones", len(active_zones),
    )


# ---------------------------------------------------------------------------
# Standalone runner (for cron)
# ---------------------------------------------------------------------------


async def main() -> None:
    """Entry point for standalone / cron execution."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from shared.db.connection import get_session

    session_factory = get_session()
    async with session_factory() as session:
        zones = await detect_gnss_zones(session)
        logger.info("Detection complete: %d zones created/updated", zones)


if __name__ == "__main__":
    asyncio.run(main())
