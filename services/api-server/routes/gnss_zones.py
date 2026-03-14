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
