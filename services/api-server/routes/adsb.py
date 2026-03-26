"""ADS-B REST endpoints.

Provides:
- GET /api/adsb/interference-zones  -- interference events as GeoJSON (replaces gnss-zones)
- GET /api/adsb/aircraft             -- current/recent positions of aircraft of interest
- GET /api/adsb/aircraft-of-interest -- catalog of tracked aircraft
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import text

from shared.db.connection import get_session

logger = logging.getLogger("api-server.adsb")

router = APIRouter(prefix="/api/adsb", tags=["adsb"])

WINDOW_HOURS = {
    "1h": 1, "3h": 3, "6h": 6, "12h": 12, "24h": 24, "3d": 72, "7d": 168,
}


@router.get("/interference-zones")
async def get_interference_zones(
    center: str | None = Query(None, description="Center of time window (ISO datetime). Default: now"),
    window: str | None = Query(None, description="Window size: 1h, 3h, 6h, 12h, 24h, 3d, 7d. Default: 24h"),
    active_only: bool = Query(False, description="Return only currently active events"),
):
    """Return ADS-B-derived interference zones as a GeoJSON FeatureCollection.

    Each feature is a Point with a radius_km property for rendering as a circle.
    Zones have time_start/time_end for playback filtering.
    """
    if center:
        center_dt = datetime.fromisoformat(center)
    else:
        center_dt = datetime.now(timezone.utc)
    if center_dt.tzinfo is None:
        center_dt = center_dt.replace(tzinfo=timezone.utc)

    half_hours = WINDOW_HOURS.get(window or "24h", 24) / 2.0
    window_start = center_dt - timedelta(hours=half_hours)
    window_end = center_dt + timedelta(hours=half_hours)

    if active_only:
        sql = """
            SELECT id, time_start, time_end, h3_index, center_lat, center_lon,
                   radius_km, severity, event_type, confidence,
                   peak_aircraft_affected, min_nac_p_observed, is_active
            FROM adsb_interference_events
            WHERE is_active = TRUE
            ORDER BY time_start DESC
        """
        params = {}
    else:
        sql = """
            SELECT id, time_start, time_end, h3_index, center_lat, center_lon,
                   radius_km, severity, event_type, confidence,
                   peak_aircraft_affected, min_nac_p_observed, is_active
            FROM adsb_interference_events
            WHERE time_start <= :window_end AND time_end >= :window_start
            ORDER BY time_start DESC
            LIMIT 5000
        """
        params = {"window_start": window_start, "window_end": window_end}

    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(text(sql), params)
        rows = result.mappings().all()

    features = []
    for row in rows:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(row["center_lon"]), float(row["center_lat"])],
            },
            "properties": {
                "id": row["id"],
                "time_start": row["time_start"].isoformat() if isinstance(row["time_start"], datetime) else str(row["time_start"]),
                "time_end": row["time_end"].isoformat() if isinstance(row["time_end"], datetime) else str(row["time_end"]),
                "h3_index": str(row["h3_index"]),
                "radius_km": float(row["radius_km"]),
                "severity": row["severity"],
                "event_type": row["event_type"],
                "confidence": float(row["confidence"]),
                "peak_aircraft_affected": row["peak_aircraft_affected"],
                "min_nac_p": row["min_nac_p_observed"],
                "is_active": row["is_active"],
            },
        })

    return {"type": "FeatureCollection", "features": features}


@router.get("/aircraft")
async def get_aircraft_positions(
    window: str | None = Query("1h", description="How far back to look: 1h, 3h, 6h, 12h, 24h"),
    max_age_minutes: int = Query(5, description="Hide aircraft not seen in this many minutes"),
    country: str | None = Query(None, description="Filter by country"),
    category: str | None = Query(None, description="Filter by category (military, police, coast_guard)"),
):
    """Return recent positions of aircraft of interest as GeoJSON.

    Returns the latest position per aircraft within the time window,
    but only if that position is within max_age_minutes of now.
    """
    hours = WINDOW_HOURS.get(window or "1h", 1)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)

    sql = """
        SELECT * FROM (
            SELECT DISTINCT ON (p.icao_hex)
                p.icao_hex, p.callsign, p.lat, p.lon,
                p.alt_baro, p.ground_speed, p.track, p.on_ground,
                p.time,
                COALESCE(p.category, a.category) AS category,
                COALESCE(p.country, a.country) AS country,
                COALESCE(p.role, a.role) AS role,
                a.registration, a.type_code, a.description AS ac_description
            FROM adsb_positions p
            LEFT JOIN aircraft_of_interest a ON a.icao_hex = p.icao_hex
            WHERE p.time >= :since
            ORDER BY p.icao_hex, p.time DESC
        ) latest
        WHERE latest.time >= :stale_cutoff
    """
    params: dict = {"since": since, "stale_cutoff": stale_cutoff}

    if country:
        sql += " AND latest.country = :country"
        params["country"] = country
    if category:
        sql += " AND latest.category = :category"
        params["category"] = category

    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(text(sql), params)
        rows = result.mappings().all()

    features = []
    for row in rows:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(row["lon"]), float(row["lat"])],
            },
            "properties": {
                "icao_hex": row["icao_hex"],
                "callsign": row["callsign"],
                "registration": row["registration"],
                "type_code": row["type_code"],
                "description": row["ac_description"],
                "alt_baro": row["alt_baro"],
                "ground_speed": float(row["ground_speed"]) if row["ground_speed"] else None,
                "track": float(row["track"]) if row["track"] else None,
                "on_ground": row["on_ground"],
                "category": row["category"],
                "country": row["country"],
                "role": row["role"],
                "time": row["time"].isoformat() if isinstance(row["time"], datetime) else str(row["time"]),
            },
        })

    return {"type": "FeatureCollection", "features": features}


@router.get("/aircraft/tracks")
async def get_all_aircraft_tracks(
    start: str = Query(..., description="Start of time range (ISO datetime)"),
    end: str = Query(..., description="End of time range (ISO datetime)"),
):
    """Return position tracks for ALL aircraft of interest in a time range.

    Returns a dict keyed by icao_hex, each containing track points and metadata.
    Used by playback to render aircraft trails alongside vessel trails.
    """
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)

    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(
            text("""
                SELECT p.time, p.icao_hex, p.callsign, p.lat, p.lon,
                       p.alt_baro, p.ground_speed, p.track, p.on_ground,
                       COALESCE(p.category, a.category) AS category,
                       COALESCE(p.country, a.country) AS country,
                       a.registration, a.type_code, a.description AS ac_description
                FROM adsb_positions p
                LEFT JOIN aircraft_of_interest a ON a.icao_hex = p.icao_hex
                WHERE p.time >= :start AND p.time <= :end
                ORDER BY p.icao_hex, p.time ASC
            """),
            {"start": start_dt, "end": end_dt},
        )
        rows = result.mappings().all()

    # Group by aircraft
    aircraft: dict = {}
    for row in rows:
        hex_code = row["icao_hex"]
        if hex_code not in aircraft:
            aircraft[hex_code] = {
                "icao_hex": hex_code,
                "callsign": row["callsign"],
                "registration": row["registration"],
                "type_code": row["type_code"],
                "description": row["ac_description"],
                "category": row["category"],
                "country": row["country"],
                "points": [],
            }
        aircraft[hex_code]["points"].append({
            "time": row["time"].isoformat(),
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "alt_baro": row["alt_baro"],
            "ground_speed": float(row["ground_speed"]) if row["ground_speed"] else None,
            "track": float(row["track"]) if row["track"] else None,
        })

    return {"aircraft": aircraft, "count": len(aircraft)}


@router.get("/aircraft/{icao_hex}/track")
async def get_aircraft_track(
    icao_hex: str,
    window: str | None = Query("24h", description="Track history window"),
):
    """Return position track for a specific aircraft."""
    hours = WINDOW_HOURS.get(window or "24h", 24)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(
            text("""
                SELECT time, lat, lon, alt_baro, ground_speed, track, on_ground
                FROM adsb_positions
                WHERE icao_hex = :hex AND time >= :since
                ORDER BY time ASC
            """),
            {"hex": icao_hex.lower(), "since": since},
        )
        rows = result.mappings().all()

    coordinates = []
    properties_list = []
    for row in rows:
        coordinates.append([float(row["lon"]), float(row["lat"])])
        properties_list.append({
            "time": row["time"].isoformat(),
            "alt_baro": row["alt_baro"],
            "ground_speed": float(row["ground_speed"]) if row["ground_speed"] else None,
        })

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates,
        } if len(coordinates) >= 2 else {
            "type": "Point",
            "coordinates": coordinates[0] if coordinates else [0, 0],
        },
        "properties": {
            "icao_hex": icao_hex.lower(),
            "point_count": len(coordinates),
            "points": properties_list,
        },
    }


@router.get("/aircraft-of-interest")
async def get_aircraft_catalog(
    country: str | None = Query(None),
    category: str | None = Query(None),
):
    """Return the aircraft of interest catalog."""
    sql = "SELECT * FROM aircraft_of_interest WHERE 1=1"
    params: dict = {}
    if country:
        sql += " AND country = :country"
        params["country"] = country
    if category:
        sql += " AND category = :category"
        params["category"] = category
    sql += " ORDER BY country, category, icao_hex"

    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(text(sql), params)
        rows = result.mappings().all()

    return {
        "count": len(rows),
        "aircraft": [
            {
                "icao_hex": row["icao_hex"],
                "registration": row["registration"],
                "type_code": row["type_code"],
                "description": row["description"],
                "country": row["country"],
                "category": row["category"],
                "role": row["role"],
            }
            for row in rows
        ],
    }
