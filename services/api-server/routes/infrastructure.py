"""Infrastructure REST endpoints for the Heimdal API server.

Provides:
- GET /api/infrastructure/routes  — infrastructure routes as GeoJSON
- GET /api/infrastructure/alerts  — vessels currently in corridors
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text

from shared.db.connection import get_session

logger = logging.getLogger("api-server.infrastructure")

router = APIRouter(prefix="/api", tags=["infrastructure"])


@router.get("/infrastructure/routes")
async def get_infrastructure_routes():
    """Return infrastructure routes as GeoJSON FeatureCollection.

    Each feature is a LineString with properties: id, name, route_type,
    operator, buffer_nm.
    """
    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(
            text(
                "SELECT id, name, route_type, operator, buffer_nm, "
                "ST_AsGeoJSON(geometry::geometry) AS geojson "
                "FROM infrastructure_routes "
                "ORDER BY name"
            )
        )
        rows = result.mappings().all()

        import json

        features = []
        for row in rows:
            geom = json.loads(row["geojson"])
            features.append(
                {
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {
                        "id": row["id"],
                        "name": row["name"],
                        "route_type": row["route_type"],
                        "operator": row["operator"],
                        "buffer_nm": row["buffer_nm"],
                    },
                }
            )

    return {"type": "FeatureCollection", "features": features}


@router.get("/infrastructure/alerts")
async def get_infrastructure_alerts():
    """Return vessels currently inside infrastructure corridors.

    Joins infrastructure_events (where exit_time IS NULL) with
    vessel_profiles and infrastructure_routes. Sorted by risk_score desc.
    """
    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(
            text(
                "SELECT ie.id, ie.mmsi, ie.route_id, ie.entry_time, "
                "ie.min_speed, ie.max_alignment, "
                "vp.ship_name AS vessel_name, vp.risk_tier, vp.risk_score, "
                "ST_Y(vp.last_position::geometry) AS lat, "
                "ST_X(vp.last_position::geometry) AS lon, "
                "ir.name AS route_name, ir.route_type "
                "FROM infrastructure_events ie "
                "JOIN vessel_profiles vp ON vp.mmsi = ie.mmsi "
                "JOIN infrastructure_routes ir ON ir.id = ie.route_id "
                "WHERE ie.exit_time IS NULL "
                "ORDER BY vp.risk_score DESC"
            )
        )
        rows = result.mappings().all()

        alerts = []
        for row in rows:
            alerts.append(
                {
                    "id": row["id"],
                    "mmsi": row["mmsi"],
                    "vessel_name": row["vessel_name"],
                    "risk_tier": row["risk_tier"],
                    "risk_score": row["risk_score"],
                    "lat": row["lat"],
                    "lon": row["lon"],
                    "route_id": row["route_id"],
                    "route_name": row["route_name"],
                    "route_type": row["route_type"],
                    "entry_time": str(row["entry_time"]),
                    "min_speed": row["min_speed"],
                    "max_alignment": row["max_alignment"],
                }
            )

    return {"alerts": alerts}
