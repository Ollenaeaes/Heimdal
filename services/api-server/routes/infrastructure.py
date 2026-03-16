"""Infrastructure REST endpoints for the Heimdal API server.

Provides:
- GET /api/infrastructure/routes  — infrastructure routes as GeoJSON
- GET /api/infrastructure/alerts  — vessels currently in corridors
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from sqlalchemy import text

from shared.db.connection import get_session

logger = logging.getLogger("api-server.infrastructure")

router = APIRouter(prefix="/api", tags=["infrastructure"])


@router.get("/infrastructure/routes")
async def get_infrastructure_routes(
    west: float = Query(-180),
    south: float = Query(-90),
    east: float = Query(180),
    north: float = Query(90),
    simplify: float = Query(0, description="Geometry simplification tolerance in degrees (0 = full detail)"),
):
    """Return infrastructure routes as GeoJSON FeatureCollection.

    Supports bbox filtering via west/south/east/north query params so the
    frontend only loads cables visible in the current viewport.
    Optional simplify parameter reduces geometry complexity for zoomed-out views.
    """
    session_factory = get_session()

    # Use simplified geometry when tolerance is set
    if simplify > 0:
        geom_expr = f"ST_AsGeoJSON(ST_SimplifyPreserveTopology(geometry::geometry, {simplify}))"
    else:
        geom_expr = "ST_AsGeoJSON(geometry::geometry)"

    async with session_factory() as session:
        result = await session.execute(
            text(
                f"SELECT id, name, route_type, operator, buffer_nm, "
                f"{geom_expr} AS geojson "
                f"FROM infrastructure_routes "
                f"WHERE ST_Intersects("
                f"  geometry::geometry, "
                f"  ST_MakeEnvelope(:west, :south, :east, :north, 4326)"
                f") "
                f"ORDER BY name"
            ),
            {"west": west, "south": south, "east": east, "north": north},
        )
        rows = result.mappings().all()

        import json

        features = []
        for row in rows:
            geojson = row["geojson"]
            if not geojson:
                continue
            geom = json.loads(geojson)
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
    """Return infrastructure corridor events — both active and recent (last 48h).

    Joins infrastructure_events with vessel_profiles and infrastructure_routes.
    Sorted by entry_time desc (most recent first).
    """
    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(
            text(
                "SELECT ie.id, ie.mmsi, ie.route_id, ie.entry_time, "
                "ie.exit_time, ie.duration_minutes, "
                "ie.min_speed, ie.max_alignment, ie.details, "
                "vp.ship_name AS vessel_name, vp.risk_tier, vp.risk_score, "
                "vp.last_lat AS lat, "
                "vp.last_lon AS lon, "
                "ir.name AS route_name, ir.route_type "
                "FROM infrastructure_events ie "
                "JOIN vessel_profiles vp ON vp.mmsi = ie.mmsi "
                "JOIN infrastructure_routes ir ON ir.id = ie.route_id "
                "WHERE ie.exit_time IS NULL "
                "   OR ie.entry_time > NOW() - INTERVAL '48 hours' "
                "ORDER BY ie.entry_time DESC"
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
                    "exit_time": str(row["exit_time"]) if row["exit_time"] else None,
                    "duration_minutes": row["duration_minutes"],
                    "min_speed": row["min_speed"],
                    "max_alignment": row["max_alignment"],
                    "active": row["exit_time"] is None,
                    "details": row["details"] or {},
                }
            )

    return {"alerts": alerts}


@router.get("/infrastructure/alerts/{alert_id}/track")
async def get_infrastructure_alert_track(alert_id: int):
    """Return the vessel track +-12 hours around an infrastructure event.

    Used to visualize what the vessel was doing before, during, and after
    the infrastructure corridor transit.
    """
    import json

    session_factory = get_session()
    async with session_factory() as session:
        # Get the event to find mmsi and entry_time
        event_result = await session.execute(
            text(
                "SELECT mmsi, entry_time, exit_time FROM infrastructure_events WHERE id = :id"
            ),
            {"id": alert_id},
        )
        event = event_result.mappings().first()
        if not event:
            from fastapi import HTTPException
            raise HTTPException(404, "Alert not found")

        center_time = event["entry_time"]
        # Fetch track +-12 hours around the event
        track_result = await session.execute(
            text(
                "SELECT ST_Y(position::geometry) AS lat, "
                "ST_X(position::geometry) AS lon, "
                "sog, cog, timestamp "
                "FROM vessel_positions "
                "WHERE mmsi = :mmsi "
                "  AND timestamp BETWEEN :start AND :end "
                "ORDER BY timestamp"
            ),
            {
                "mmsi": event["mmsi"],
                "start": f"{center_time}::timestamptz - INTERVAL '12 hours'",
                "end": f"{center_time}::timestamptz + INTERVAL '12 hours'",
            },
        )

        # Use parameterized interval calculation
        track_result2 = await session.execute(
            text(
                "SELECT ST_Y(position::geometry) AS lat, "
                "ST_X(position::geometry) AS lon, "
                "sog, cog, timestamp "
                "FROM vessel_positions "
                "WHERE mmsi = :mmsi "
                "  AND timestamp BETWEEN :center - INTERVAL '12 hours' "
                "                   AND :center + INTERVAL '12 hours' "
                "ORDER BY timestamp"
            ),
            {
                "mmsi": event["mmsi"],
                "center": center_time,
            },
        )
        rows = track_result2.mappings().all()

    return {
        "mmsi": event["mmsi"],
        "event_entry_time": str(center_time),
        "event_exit_time": str(event["exit_time"]) if event["exit_time"] else None,
        "track": [
            {
                "lat": row["lat"],
                "lon": row["lon"],
                "sog": row["sog"],
                "cog": row["cog"],
                "timestamp": str(row["timestamp"]),
            }
            for row in rows
        ],
    }
