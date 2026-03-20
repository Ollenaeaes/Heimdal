"""Maritime zones REST endpoints for the Heimdal API server.

Provides:
- GET /api/maritime-zones/boundaries — EEZ/12nm boundary lines as GeoJSON (for map display)
- GET /api/maritime-zones/lookup      — Which zone(s) contain a given point (for backend logic)
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Query
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
