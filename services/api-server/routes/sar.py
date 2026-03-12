"""SAR detection endpoints for the Heimdal API server.

Provides:
- GET /api/sar/detections — paginated SAR detection list with optional filters
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query

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
        description="Bounding box filter: min_lon,min_lat,max_lon,max_lat",
    ),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Return paginated SAR detections with optional filters.

    Supports filtering by ``is_dark``, ``source``, and spatial ``bbox``.
    The bbox parameter should be a comma-separated string of
    ``min_lon,min_lat,max_lon,max_lat``.
    """
    session_factory = get_session()
    async with session_factory() as session:
        rows = await list_sar_detections(
            session,
            is_dark=is_dark,
            source=source,
            limit=limit,
            offset=offset,
        )

    # Apply bbox filter in-memory on the already-extracted lat/lon columns
    if bbox:
        try:
            parts = [float(x.strip()) for x in bbox.split(",")]
            if len(parts) != 4:
                raise ValueError("bbox must have exactly 4 values")
            min_lon, min_lat, max_lon, max_lat = parts
            rows = [
                r
                for r in rows
                if (
                    r.get("lat") is not None
                    and r.get("lon") is not None
                    and min_lat <= r["lat"] <= max_lat
                    and min_lon <= r["lon"] <= max_lon
                )
            ]
        except (ValueError, TypeError):
            logger.warning("Invalid bbox parameter: %s", bbox)
            # Return unfiltered results on bad bbox rather than erroring

    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset}
