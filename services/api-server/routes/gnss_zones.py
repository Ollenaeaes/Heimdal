"""GNSS interference zones REST endpoint.

Provides:
- GET /api/gnss-zones  -- returns GNSS interference zones as GeoJSON with time-window queries
- GET /api/gnss-spoofing-events -- returns spoofing event point data for heatmap
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from shared.db.connection import get_session

logger = logging.getLogger("api-server.gnss_zones")

router = APIRouter(prefix="/api", tags=["gnss"])

WINDOW_HOURS = {
    "6h": 6,
    "12h": 12,
    "24h": 24,
    "3d": 72,
    "7d": 168,
}


def parse_window(window: str) -> int:
    """Return window size in hours."""
    return WINDOW_HOURS.get(window, 24)


def parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    """Parse bbox string 'south,west,north,east' into four floats.

    Raises ValueError on invalid input.
    """
    parts = bbox.split(",")
    if len(parts) != 4:
        raise ValueError("bbox must have exactly 4 comma-separated values: south,west,north,east")
    south, west, north, east = (float(p.strip()) for p in parts)
    return south, west, north, east


@router.get("/gnss-zones")
async def get_gnss_zones(
    center: str | None = Query(None, description="Center of time window (ISO datetime). Default: now"),
    window: str | None = Query(None, description="Window size: 6h, 12h, 24h, 3d, 7d. Default: 24h"),
    bbox: str | None = Query(None, description="Bounding box as 'south,west,north,east'"),
):
    """Return GNSS interference zones as a GeoJSON FeatureCollection.

    Supports time-window queries with center ± window/2.
    """
    # Parse center time
    if center:
        try:
            center_dt = datetime.fromisoformat(center)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid center datetime format. Use ISO 8601.")
    else:
        center_dt = datetime.now(timezone.utc)

    # Ensure timezone-aware
    if center_dt.tzinfo is None:
        center_dt = center_dt.replace(tzinfo=timezone.utc)

    # Parse window
    window_str = window or "24h"
    half_hours = parse_window(window_str) / 2.0
    window_start = center_dt - timedelta(hours=half_hours)
    window_end = center_dt + timedelta(hours=half_hours)

    # Parse bbox if provided
    bbox_values = None
    if bbox:
        try:
            bbox_values = parse_bbox(bbox)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Build query
    sql = (
        "SELECT id, detected_at, expires_at, affected_count, affected_mmsis, "
        "event_type, peak_severity, details, "
        "ST_AsGeoJSON(geometry)::json AS geojson "
        "FROM gnss_interference_zones "
        "WHERE detected_at <= :window_end AND expires_at >= :window_start"
    )
    params: dict = {
        "window_start": window_start,
        "window_end": window_end,
    }

    if bbox_values is not None:
        south, west, north, east = bbox_values
        sql += " AND ST_Intersects(geometry, ST_MakeEnvelope(:west, :south, :east, :north, 4326)::geography)"
        params["south"] = south
        params["west"] = west
        params["north"] = north
        params["east"] = east

    sql += " ORDER BY detected_at DESC"

    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(text(sql), params)
        rows = result.mappings().all()

    features = []
    for row in rows:
        properties = {
            "id": row["id"],
            "detected_at": row["detected_at"].isoformat() if isinstance(row["detected_at"], datetime) else str(row["detected_at"]),
            "expires_at": row["expires_at"].isoformat() if isinstance(row["expires_at"], datetime) else str(row["expires_at"]),
            "affected_count": row["affected_count"],
            "affected_mmsis": list(row["affected_mmsis"]) if row["affected_mmsis"] else [],
            "event_type": row["event_type"],
            "peak_severity": row["peak_severity"],
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


@router.get("/gnss-positions")
async def get_gnss_spoofed_positions(
    center: str | None = Query(None, description="Center of time window (ISO datetime). Default: now"),
    window: str | None = Query(None, description="Window size: 1h, 3h, 6h. Default: 1h"),
):
    """Return spoofed vessel positions as GeoJSON points for dot-based rendering.

    Returns two point types per spoofed position:
    - spoofed: where GPS says the vessel is (red dots)
    - real: interpolated actual position (cyan dots)
    """
    window_hours_map = {"1h": 1, "3h": 3, "6h": 6}
    wh = window_hours_map.get(window or "1h", 1)

    if center:
        try:
            center_dt = datetime.fromisoformat(center)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid center datetime")
    else:
        center_dt = datetime.now(timezone.utc)

    half = timedelta(hours=wh / 2)
    window_start = center_dt - half
    window_end = center_dt + half

    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(
            text("""
                SELECT mmsi, detected_at, spoofed_lat, spoofed_lon,
                       real_lat, real_lon, event_type, deviation_km
                FROM gnss_spoofed_positions
                WHERE detected_at BETWEEN :ws AND :we
                ORDER BY detected_at
            """),
            {"ws": window_start, "we": window_end},
        )
        rows = result.mappings().all()

    features = []
    for row in rows:
        # Spoofed position (where GPS says vessel is)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(row["spoofed_lon"]), float(row["spoofed_lat"])]},
            "properties": {
                "mmsi": row["mmsi"],
                "detected_at": row["detected_at"].isoformat(),
                "point_type": "spoofed",
                "event_type": row["event_type"],
                "deviation_km": float(row["deviation_km"]) if row["deviation_km"] else None,
            },
        })
        # Real position (interpolated actual location)
        if row["real_lat"] is not None and row["real_lon"] is not None:
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(row["real_lon"]), float(row["real_lat"])]},
                "properties": {
                    "mmsi": row["mmsi"],
                    "detected_at": row["detected_at"].isoformat(),
                    "point_type": "real",
                    "event_type": row["event_type"],
                    "deviation_km": float(row["deviation_km"]) if row["deviation_km"] else None,
                },
            })

    return {"type": "FeatureCollection", "features": features}


@router.get("/gnss-spoofing-events")
async def get_spoofing_events(start: str | None = None, end: str | None = None):
    """Return spoofing event locations for heatmap rendering.

    Query params:
      start: ISO datetime for window start (default: 7 days ago)
      end:   ISO datetime for window end (default: now)
    """
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
                    'spoof_land_position', 'spoof_duplicate_mmsi',
                    'spoof_identity_mismatch'
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
