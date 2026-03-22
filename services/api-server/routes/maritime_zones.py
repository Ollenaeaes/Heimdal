"""Maritime zones REST endpoints for the Heimdal API server.

Provides:
- GET /api/maritime-zones/boundaries — EEZ/12nm boundary lines as GeoJSON (for map display)
- GET /api/maritime-zones/lookup      — Which zone(s) contain a given point (for backend logic)
- GET /api/maritime-zones/eez-report — Sanctioned vessels in an EEZ during a time range
- GET /api/maritime-zones/countries  — List of countries with EEZ data for dropdown
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from shared.db.connection import get_session

logger = logging.getLogger("api-server.maritime_zones")

router = APIRouter(prefix="/api", tags=["maritime-zones"])


@router.get("/maritime-zones/boundaries")
async def get_maritime_boundaries(
    zone_type: str | None = Query(None, description="Filter: 'eez' or '12nm'"),
    west: float = Query(-180),
    south: float = Query(-90),
    east: float = Query(180),
    north: float = Query(90),
    simplify: float = Query(0.01, description="Simplification tolerance in degrees"),
):
    """Return maritime boundary lines as GeoJSON FeatureCollection.

    EEZ boundaries come from the pre-computed boundary lines table.
    12nm boundaries are extracted as polygon outlines from the zones table
    (with aggressive simplification since these are complex coastlines).
    """
    session_factory = get_session()
    features = []

    async with session_factory() as session:
        # --- EEZ boundary lines (from maritime_boundaries table) ---
        if zone_type in (None, "eez"):
            if simplify > 0:
                geom_expr = f"ST_AsGeoJSON(ST_SimplifyPreserveTopology(geometry::geometry, {simplify}))"
            else:
                geom_expr = "ST_AsGeoJSON(geometry::geometry)"

            result = await session.execute(
                text(
                    f"SELECT id, line_name, line_type, "
                    f"sovereign1, sovereign2, eez1, eez2, length_km, "
                    f"{geom_expr} AS geojson "
                    f"FROM maritime_boundaries "
                    f"WHERE boundary_type = 'eez' "
                    f"  AND ST_Intersects("
                    f"    geometry::geometry, "
                    f"    ST_MakeEnvelope(:west, :south, :east, :north, 4326)"
                    f"  ) "
                    f"ORDER BY line_name"
                ),
                {"west": west, "south": south, "east": east, "north": north},
            )
            for row in result.mappings().all():
                geojson = row["geojson"]
                if not geojson:
                    continue
                geom = json.loads(geojson)
                features.append({
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {
                        "id": row["id"],
                        "boundary_type": "eez",
                        "name": row["line_name"] or "",
                        "sovereign1": row["sovereign1"],
                        "sovereign2": row["sovereign2"],
                    },
                })

        # --- 12nm boundaries (extracted as polygon outlines from maritime_zones) ---
        if zone_type in (None, "12nm"):
            # Use heavier simplification for 12nm since these are full coastline polygons
            tol_12nm = max(simplify, 0.1)
            result = await session.execute(
                text(
                    f"SELECT id, geoname, sovereign, iso_sov, "
                    f"ST_AsGeoJSON("
                    f"  ST_Boundary("
                    f"    ST_SimplifyPreserveTopology(geometry::geometry, {tol_12nm})"
                    f"  )"
                    f") AS geojson "
                    f"FROM maritime_zones "
                    f"WHERE zone_type = '12nm' "
                    f"  AND ST_Intersects("
                    f"    geometry::geometry, "
                    f"    ST_MakeEnvelope(:west, :south, :east, :north, 4326)"
                    f"  ) "
                    f"ORDER BY geoname"
                ),
                {"west": west, "south": south, "east": east, "north": north},
            )
            for row in result.mappings().all():
                geojson = row["geojson"]
                if not geojson:
                    continue
                geom = json.loads(geojson)
                # ST_Boundary of MultiPolygon produces MultiLineString or GeometryCollection
                # Filter out empty geometries
                if geom.get("type") == "GeometryCollection":
                    # Flatten into individual linestrings
                    for sub_geom in geom.get("geometries", []):
                        if sub_geom.get("type") in ("LineString", "MultiLineString"):
                            features.append({
                                "type": "Feature",
                                "geometry": sub_geom,
                                "properties": {
                                    "id": row["id"],
                                    "boundary_type": "12nm",
                                    "name": row["geoname"] or "",
                                    "sovereign1": row["sovereign"],
                                    "sovereign2": None,
                                },
                            })
                elif geom.get("type") in ("LineString", "MultiLineString"):
                    features.append({
                        "type": "Feature",
                        "geometry": geom,
                        "properties": {
                            "id": row["id"],
                            "boundary_type": "12nm",
                            "name": row["geoname"] or "",
                            "sovereign1": row["sovereign"],
                            "sovereign2": None,
                        },
                    })

    return {"type": "FeatureCollection", "features": features}


@router.get("/maritime-zones/lookup")
async def lookup_maritime_zone(
    lon: float = Query(..., description="Longitude"),
    lat: float = Query(..., description="Latitude"),
    zone_type: str | None = Query(None, description="Filter: 'eez' or '12nm'"),
):
    """Look up which maritime zone(s) contain a given point.

    Used by backend scoring rules to determine if a vessel is in
    territorial waters or an EEZ, and whose jurisdiction it falls under.
    """
    session_factory = get_session()

    where = "ST_Intersects(geometry, ST_MakePoint(:lon, :lat)::geography)"
    params: dict = {"lon": lon, "lat": lat}

    if zone_type:
        where += " AND zone_type = :zone_type"
        params["zone_type"] = zone_type

    async with session_factory() as session:
        result = await session.execute(
            text(
                f"SELECT id, zone_type, mrgid, geoname, sovereign, iso_sov, "
                f"territory, iso_ter, pol_type, area_km2 "
                f"FROM maritime_zones "
                f"WHERE {where} "
                f"ORDER BY zone_type"
            ),
            params,
        )
        rows = result.mappings().all()

    return {
        "lon": lon,
        "lat": lat,
        "zones": [
            {
                "id": row["id"],
                "zone_type": row["zone_type"],
                "geoname": row["geoname"],
                "sovereign": row["sovereign"],
                "iso_sov": row["iso_sov"],
                "territory": row["territory"],
                "iso_ter": row["iso_ter"],
            }
            for row in rows
        ],
    }


@router.get("/maritime-zones/countries")
async def list_eez_countries():
    """Return a list of countries that have EEZ zone data, for use in dropdowns."""
    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(
            text(
                "SELECT DISTINCT iso_sov, sovereign "
                "FROM maritime_zones "
                "WHERE zone_type = 'eez' AND iso_sov IS NOT NULL "
                "ORDER BY sovereign"
            )
        )
        rows = result.mappings().all()

    return [
        {"iso": row["iso_sov"], "name": row["sovereign"]}
        for row in rows
    ]


@router.get("/maritime-zones/eez-report")
async def eez_sanctioned_report(
    iso_sov: str = Query(..., description="ISO country code (e.g. 'DNK' for Denmark)"),
    hours: Optional[float] = Query(None, description="Lookback hours (alternative to start/end)"),
    start: Optional[datetime] = Query(None, description="Start of time range (ISO 8601)"),
    end: Optional[datetime] = Query(None, description="End of time range (ISO 8601)"),
):
    """Report unique sanctioned vessels that had positions inside a country's EEZ.

    Finds all vessel_positions that intersect the country's EEZ geometry within
    the time range, then filters to vessels with sanctions matches. Returns
    unique vessels with their details and any port calls in the same period.
    """
    # Resolve time range
    if hours is not None:
        t_end = datetime.now(timezone.utc)
        t_start = t_end - timedelta(hours=hours)
    elif start is not None and end is not None:
        t_start = start
        t_end = end
    else:
        raise HTTPException(status_code=400, detail="Provide either 'hours' or both 'start' and 'end'")

    # Clamp to max 90 days
    max_range = timedelta(days=90)
    if t_end - t_start > max_range:
        t_start = t_end - max_range

    session_factory = get_session()
    async with session_factory() as session:
        # Set a generous timeout — this query touches a lot of data
        await session.execute(text("SET LOCAL statement_timeout = '60s'"))

        # Step 1: Find unique sanctioned MMSIs with positions in this EEZ
        vessel_query = text(
            "SELECT DISTINCT vp_pos.mmsi "
            "FROM vessel_positions vp_pos "
            "JOIN maritime_zones mz ON ST_Intersects(vp_pos.position, mz.geometry) "
            "JOIN vessel_profiles vp ON vp_pos.mmsi = vp.mmsi "
            "WHERE mz.zone_type = 'eez' "
            "  AND mz.iso_sov = :iso_sov "
            "  AND vp_pos.timestamp BETWEEN :start AND :end "
            "  AND vp.sanctions_status IS NOT NULL "
            "  AND vp.sanctions_status != '{}' "
            "  AND jsonb_array_length(COALESCE(vp.sanctions_status->'matches', '[]'::jsonb)) > 0"
        )

        try:
            result = await session.execute(vessel_query, {
                "iso_sov": iso_sov.upper(),
                "start": t_start,
                "end": t_end,
            })
            mmsis = [row["mmsi"] for row in result.mappings().all()]
        except Exception as exc:
            logger.warning("EEZ report query failed: %s", exc)
            raise HTTPException(
                status_code=504,
                detail="Query timed out — try a shorter time range",
            )

        if not mmsis:
            # Get zone name for the response even if no vessels found
            zone_result = await session.execute(
                text(
                    "SELECT geoname, sovereign FROM maritime_zones "
                    "WHERE zone_type = 'eez' AND iso_sov = :iso_sov LIMIT 1"
                ),
                {"iso_sov": iso_sov.upper()},
            )
            zone_row = zone_result.mappings().first()
            return {
                "zone": {
                    "iso_sov": iso_sov.upper(),
                    "name": zone_row["geoname"] if zone_row else iso_sov.upper(),
                    "sovereign": zone_row["sovereign"] if zone_row else iso_sov.upper(),
                },
                "time_range": {"start": t_start.isoformat(), "end": t_end.isoformat()},
                "total_sanctioned_vessels": 0,
                "vessels": [],
            }

        # Step 2: Get vessel details for all found MMSIs
        detail_query = text(
            "SELECT mmsi, imo, ship_name, ship_type_text, flag_country, "
            "risk_tier, risk_score, sanctions_status, "
            "last_lat, last_lon, last_position_time, "
            "length, width, owner, operator "
            "FROM vessel_profiles "
            "WHERE mmsi = ANY(:mmsis)"
        )
        detail_result = await session.execute(detail_query, {"mmsis": mmsis})
        vessel_rows = detail_result.mappings().all()

        # Step 3: Get port calls for these vessels in the time range
        port_query = text(
            "SELECT mmsi, port_name, lat, lon, start_time, end_time, details "
            "FROM gfw_events "
            "WHERE event_type = 'port_visit' "
            "  AND mmsi = ANY(:mmsis) "
            "  AND start_time BETWEEN :start AND :end "
            "ORDER BY start_time DESC"
        )
        port_result = await session.execute(port_query, {
            "mmsis": mmsis,
            "start": t_start,
            "end": t_end,
        })
        port_rows = port_result.mappings().all()

        # Group port calls by MMSI
        port_calls_by_mmsi: dict[int, list] = {}
        for pr in port_rows:
            m = pr["mmsi"]
            if m not in port_calls_by_mmsi:
                port_calls_by_mmsi[m] = []
            port_calls_by_mmsi[m].append({
                "port_name": pr["port_name"],
                "lat": pr["lat"],
                "lon": pr["lon"],
                "start_time": pr["start_time"].isoformat() if pr["start_time"] else None,
                "end_time": pr["end_time"].isoformat() if pr["end_time"] else None,
            })

        # Get zone metadata
        zone_result = await session.execute(
            text(
                "SELECT geoname, sovereign FROM maritime_zones "
                "WHERE zone_type = 'eez' AND iso_sov = :iso_sov LIMIT 1"
            ),
            {"iso_sov": iso_sov.upper()},
        )
        zone_row = zone_result.mappings().first()

    # Build response
    vessels = []
    for vr in vessel_rows:
        sanctions = vr["sanctions_status"] or {}
        matches = sanctions.get("matches", []) if isinstance(sanctions, dict) else []
        vessels.append({
            "mmsi": vr["mmsi"],
            "imo": vr["imo"],
            "name": vr["ship_name"],
            "ship_type": vr["ship_type_text"],
            "flag": vr["flag_country"],
            "risk_tier": vr["risk_tier"],
            "risk_score": vr["risk_score"],
            "sanctions_programs": list({m.get("program", "unknown") for m in matches}),
            "sanctions_match_count": len(matches),
            "last_lat": vr["last_lat"],
            "last_lon": vr["last_lon"],
            "last_position_time": vr["last_position_time"].isoformat() if vr["last_position_time"] else None,
            "length": vr["length"],
            "width": vr["width"],
            "owner": vr["owner"],
            "operator": vr["operator"],
            "port_calls": port_calls_by_mmsi.get(vr["mmsi"], []),
        })

    # Sort by risk score descending
    vessels.sort(key=lambda v: v["risk_score"] or 0, reverse=True)

    return {
        "zone": {
            "iso_sov": iso_sov.upper(),
            "name": zone_row["geoname"] if zone_row else iso_sov.upper(),
            "sovereign": zone_row["sovereign"] if zone_row else iso_sov.upper(),
        },
        "time_range": {"start": t_start.isoformat(), "end": t_end.isoformat()},
        "total_sanctioned_vessels": len(vessels),
        "vessels": vessels,
    }
