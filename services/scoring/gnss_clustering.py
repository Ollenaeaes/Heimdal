"""GNSS Interference Zone Clustering.

Post-scoring module that groups spoofing events into geographic zones.
NOT a scoring rule — called after spoof_* rules fire.

When 3+ spoofing events occur within 20nm and 1 hour, a GNSS interference
zone is created using the convex hull of the event positions. Existing
zones within 24 hours are refreshed rather than duplicated.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_EVENTS_FOR_ZONE = 3
_CLUSTER_RADIUS_NM = 20.0
_CLUSTER_RADIUS_M = _CLUSTER_RADIUS_NM * 1852  # Convert to metres
_CLUSTER_TIME_WINDOW_HOURS = 1.0
_ZONE_REFRESH_HOURS = 24.0
_ZONE_EXPIRY_HOURS = 24.0


async def cluster_spoofing_events(
    session: AsyncSession,
    events: Sequence[dict[str, Any]],
) -> int:
    """Cluster spoofing events into GNSS interference zones.

    Parameters
    ----------
    session:
        Active database session.
    events:
        List of spoofing event dicts, each containing at minimum:
        - lat: float
        - lon: float
        - timestamp: datetime or ISO string
        - rule_id: str (must start with 'spoof_')

    Returns
    -------
    Number of zones created or refreshed.
    """
    # Filter to only spoofing events with valid positions
    spoof_events = [
        e for e in events
        if e.get("rule_id", "").startswith("spoof_")
        and e.get("lat") is not None
        and e.get("lon") is not None
        and e.get("timestamp") is not None
    ]

    if len(spoof_events) < _MIN_EVENTS_FOR_ZONE:
        return 0

    # Parse timestamps
    for e in spoof_events:
        ts = e["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        if isinstance(ts, datetime) and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        e["_parsed_ts"] = ts

    # Sort by timestamp
    spoof_events.sort(key=lambda e: e["_parsed_ts"])

    # Find clusters: events within radius AND time window
    clusters = _find_clusters(spoof_events)

    zones_affected = 0
    for cluster in clusters:
        if len(cluster) < _MIN_EVENTS_FOR_ZONE:
            continue

        zones_affected += await _create_or_refresh_zone(session, cluster)

    return zones_affected


def _find_clusters(events: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group events into spatial-temporal clusters.

    Simple greedy approach: for each event, collect all events within
    the radius and time window. Overlapping clusters are merged.
    """
    from services.scoring.rules.ais_spoofing import haversine_nm

    used = set()
    clusters: list[list[dict[str, Any]]] = []

    for i, event in enumerate(events):
        if i in used:
            continue

        cluster = [event]
        used.add(i)

        for j in range(i + 1, len(events)):
            if j in used:
                continue

            other = events[j]

            # Time window check
            time_delta = abs(
                (event["_parsed_ts"] - other["_parsed_ts"]).total_seconds()
            )
            if time_delta > _CLUSTER_TIME_WINDOW_HOURS * 3600:
                continue

            # Distance check
            dist = haversine_nm(
                event["lat"], event["lon"],
                other["lat"], other["lon"],
            )
            if dist <= _CLUSTER_RADIUS_NM:
                cluster.append(other)
                used.add(j)

        clusters.append(cluster)

    return clusters


async def _create_or_refresh_zone(
    session: AsyncSession,
    cluster: list[dict[str, Any]],
) -> int:
    """Create a new zone or refresh an existing one nearby."""
    now = datetime.now(timezone.utc)
    centroid_lat = sum(e["lat"] for e in cluster) / len(cluster)
    centroid_lon = sum(e["lon"] for e in cluster) / len(cluster)

    # Check for existing zone within 24h and nearby
    existing = await session.execute(
        text("""
            SELECT id, affected_count FROM gnss_interference_zones
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
            "min_time": now - timedelta(hours=_ZONE_REFRESH_HOURS),
            "lat": centroid_lat,
            "lon": centroid_lon,
            "buffer": _CLUSTER_RADIUS_M,
        },
    )
    row = existing.first()

    if row:
        # Refresh existing zone
        zone_id, affected_count = row[0], row[1]
        await session.execute(
            text("""
                UPDATE gnss_interference_zones
                SET expires_at = :expires_at,
                    affected_count = :affected_count,
                    details = details || :new_details
                WHERE id = :zone_id
            """),
            {
                "zone_id": zone_id,
                "expires_at": now + timedelta(hours=_ZONE_EXPIRY_HOURS),
                "affected_count": affected_count + len(cluster),
                "new_details": f'{{"refreshed_at": "{now.isoformat()}", "new_events": {len(cluster)}}}',
            },
        )
        logger.info(
            "Refreshed GNSS interference zone %d with %d new events",
            zone_id, len(cluster),
        )
        return 1

    # Build point collection for convex hull
    points_sql = ", ".join(
        f"ST_SetSRID(ST_MakePoint({e['lon']}, {e['lat']}), 4326)"
        for e in cluster
    )

    await session.execute(
        text(f"""
            INSERT INTO gnss_interference_zones (
                detected_at, expires_at, geometry, affected_count, details
            ) VALUES (
                :detected_at,
                :expires_at,
                ST_ConvexHull(ST_Collect(ARRAY[{points_sql}]))::geography,
                :affected_count,
                :details
            )
        """),
        {
            "detected_at": now,
            "expires_at": now + timedelta(hours=_ZONE_EXPIRY_HOURS),
            "affected_count": len(cluster),
            "details": f'{{"rule_ids": {list(set(e.get("rule_id", "") for e in cluster))}}}',
        },
    )
    logger.info(
        "Created new GNSS interference zone with %d events near (%.4f, %.4f)",
        len(cluster), centroid_lat, centroid_lon,
    )
    return 1
