"""SAR detection endpoints for the Heimdal API server.

Provides:
- GET /api/sar/detections — paginated SAR detection list with optional filters
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from shared.db.connection import get_session
from shared.db.repositories import list_sar_detections

logger = logging.getLogger("api-server.sar")

router = APIRouter(prefix="/api/sar", tags=["sar"])


@router.get("/detections")
async def get_sar_detections(
    is_dark: Optional[bool] = Query(None, description="Filter by dark vessel status"),
    source: Optional[str] = Query(None, description="Filter by detection source"),
    bbox: Optional[str] = Query(
        None,
        description="Bounding box filter: sw_lat,sw_lon,ne_lat,ne_lon",
    ),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=1000),
):
    """Return paginated SAR detections with optional filters.

    Supports filtering by ``is_dark``, ``source``, and spatial ``bbox``.
    The bbox parameter should be a comma-separated string of
    ``sw_lat,sw_lon,ne_lat,ne_lon``.
    """
    offset = (page - 1) * per_page

    session_factory = get_session()
    async with session_factory() as session:
        rows = await list_sar_detections(
            session,
            is_dark=is_dark,
            source=source,
            limit=per_page,
            offset=offset,
        )

    # Apply bbox filter in-memory on the already-extracted lat/lon columns
    if bbox:
        parts = bbox.split(",")
        if len(parts) != 4:
            raise HTTPException(status_code=400, detail="bbox must be sw_lat,sw_lon,ne_lat,ne_lon")
        try:
            sw_lat, sw_lon, ne_lat, ne_lon = (float(p.strip()) for p in parts)
        except ValueError:
            raise HTTPException(status_code=400, detail="bbox values must be numeric")
        rows = [
            r
            for r in rows
            if (
                r.get("lat") is not None
                and r.get("lon") is not None
                and sw_lat <= r["lat"] <= ne_lat
                and sw_lon <= r["lon"] <= ne_lon
            )
        ]

    # Transform to frontend-expected camelCase format
    items = []
    for r in rows:
        items.append({
            "id": str(r.get("id", r.get("gfw_detection_id", ""))),
            "detectedAt": r["detection_time"].isoformat() if r.get("detection_time") else None,
            "lat": r.get("lat"),
            "lon": r.get("lon"),
            "estimatedLength": r.get("length_m"),
            "isDark": r.get("is_dark", False),
            "matchingScore": r.get("matching_score"),
            "fishingScore": r.get("fishing_score"),
            "matchedMmsi": r.get("matched_mmsi"),
            "matchedCategory": r.get("matched_category"),
            "matchedVesselName": None,
            "satellite": r.get("source"),
            "imageUrl": None,
        })

    return items
