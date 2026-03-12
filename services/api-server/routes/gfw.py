"""GFW (Global Fishing Watch) event endpoints for the Heimdal API server.

Provides:
- GET /api/gfw/events — paginated GFW events list with optional filters
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from shared.db.connection import get_session
from shared.db.repositories import list_gfw_events

logger = logging.getLogger("api-server.gfw")

router = APIRouter(prefix="/api/gfw", tags=["gfw"])


@router.get("/events")
async def get_gfw_events(
    event_type: Optional[str] = Query(None, description="Filter by event type (e.g. ENCOUNTER, LOITERING)"),
    mmsi: Optional[int] = Query(None, description="Filter by vessel MMSI"),
    start: Optional[datetime] = Query(None, description="Filter events starting after this time"),
    end: Optional[datetime] = Query(None, description="Filter events ending before this time"),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=1000),
):
    """Return paginated GFW events with optional filters.

    Supports filtering by ``event_type``, ``mmsi``, and time range
    (``start`` / ``end``).
    """
    offset = (page - 1) * per_page

    session_factory = get_session()
    async with session_factory() as session:
        rows = await list_gfw_events(
            session,
            event_type=event_type,
            mmsi=mmsi,
            start_after=start,
            limit=per_page,
            offset=offset,
        )

    # Apply end-time filter in-memory (the repository only supports start_after)
    if end:
        rows = [
            r for r in rows
            if r.get("start_time") is not None and r["start_time"] <= end
        ]

    return {"items": rows, "total": len(rows), "page": page, "per_page": per_page}
