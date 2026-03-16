"""GNSS interference zones REST endpoint.

Provides:
- GET /api/gnss-zones  -- returns active (non-expired) GNSS interference zones as GeoJSON
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import text

from shared.db.connection import get_session

logger = logging.getLogger("api-server.gnss_zones")

router = APIRouter(prefix="/api", tags=["gnss"])


@router.get("/gnss-zones")
async def get_gnss_zones():
    """Return active GNSS interference zones as a GeoJSON FeatureCollection.

    Only returns zones whose expires_at is in the future.
    """
    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(
            text(
                "SELECT id, detected_at, expires_at, affected_count, details, "
                "ST_AsGeoJSON(geometry)::json AS geojson "
                "FROM gnss_interference_zones "
                "WHERE expires_at > NOW() "
                "ORDER BY detected_at DESC"
            ),
        )
        rows = result.mappings().all()

    features = []
    for row in rows:
        properties = {
            "id": row["id"],
            "detected_at": row["detected_at"].isoformat() if isinstance(row["detected_at"], datetime) else str(row["detected_at"]),
            "expires_at": row["expires_at"].isoformat() if isinstance(row["expires_at"], datetime) else str(row["expires_at"]),
            "affected_count": row["affected_count"],
            "details": row["details"] if row["details"] else {},
        }

        geometry = row["geojson"] if isinstance(row["geojson"], dict) else json.loads(row["geojson"]) if row["geojson"] else None

        features.append({
            "type": "Feature",
            "properties": properties,
            "geometry": geometry,
        })

    return {
        "type": "FeatureCollection",
        "features": features,
    }


@router.get("/gnss-spoofing-events")
async def get_spoofing_events(start: str | None = None, end: str | None = None):
    """Return spoofing event locations for heatmap rendering.

    Query params:
      start: ISO datetime for window start (default: 7 days ago)
      end:   ISO datetime for window end (default: now)
    """
    from datetime import timezone, timedelta

    if end:
        end_dt = datetime.fromisoformat(end)
    else:
        end_dt = datetime.now(timezone.utc)

    if start:
        start_dt = datetime.fromisoformat(start)
    else:
        start_dt = end_dt - timedelta(days=7)

    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(
            text("""
                SELECT ae.mmsi, ae.rule_id, ae.points, ae.severity,
                    ae.created_at,
                    COALESCE(
                        (ae.details->>'lat')::float,
                        (ae.details->>'latest_land_lat')::float,
                        vp.last_lat
                    ) AS lat,
                    COALESCE(
                        (ae.details->>'lon')::float,
                        (ae.details->>'latest_land_lon')::float,
                        vp.last_lon
                    ) AS lon,
                    vp.ship_name
                FROM anomaly_events ae
                JOIN vessel_profiles vp ON vp.mmsi = ae.mmsi
                WHERE ae.rule_id IN (
                    'spoof_land_position', 'spoof_impossible_speed',
                    'spoof_frozen_position', 'spoof_duplicate_mmsi',
                    'spoof_identity_mismatch', 'ais_spoofing'
                )
                AND ae.created_at >= :start AND ae.created_at <= :end_dt
                ORDER BY ae.created_at DESC
                LIMIT 10000
            """),
            {"start": start_dt, "end_dt": end_dt},
        )
        rows = result.mappings().all()

    points = []
    for row in rows:
        lat = row["lat"]
        lon = row["lon"]
        if lat is None or lon is None:
            continue
        points.append({
            "lat": lat,
            "lon": lon,
            "mmsi": row["mmsi"],
            "rule": row["rule_id"],
            "severity": row["severity"],
            "ship_name": row["ship_name"],
            "time": row["created_at"].isoformat() if row["created_at"] else None,
        })

    return {
        "points": points,
        "count": len(points),
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
    }
