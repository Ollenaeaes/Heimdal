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

        # Batch-fetch vessel info for all MMSIs (vessel + encounter partners)
        all_mmsis = set()
        for r in rows:
            if r.get("mmsi"):
                all_mmsis.add(r["mmsi"])
            if r.get("encounter_mmsi"):
                all_mmsis.add(r["encounter_mmsi"])

        vessel_lookup: dict = {}
        if all_mmsis:
            from sqlalchemy import text
            vp_result = await session.execute(
                text(
                    "SELECT mmsi, ship_name, flag_country, ship_type_text, "
                    "risk_tier, risk_score "
                    "FROM vessel_profiles WHERE mmsi = ANY(:mmsis)"
                ),
                {"mmsis": list(all_mmsis)},
            )
            for v in vp_result.mappings().all():
                vessel_lookup[v["mmsi"]] = dict(v)

    # Transform to frontend-expected camelCase format
    items = []
    for r in rows:
        start_time = r.get("start_time")
        end_time = r.get("end_time")
        duration_hours = None
        if start_time and end_time:
            try:
                delta = end_time - start_time
                duration_hours = round(delta.total_seconds() / 3600, 1)
            except Exception:
                pass

        vessel = vessel_lookup.get(r.get("mmsi")) if r.get("mmsi") else None
        partner = vessel_lookup.get(r.get("encounter_mmsi")) if r.get("encounter_mmsi") else None

        items.append({
            "id": str(r.get("id", r.get("gfw_event_id", ""))),
            "type": r.get("event_type"),
            "startTime": start_time.isoformat() if start_time else None,
            "endTime": end_time.isoformat() if end_time else None,
            "lat": r.get("lat"),
            "lon": r.get("lon"),
            "vesselMmsi": r.get("mmsi"),
            "vesselName": vessel["ship_name"] if vessel else None,
            "vesselFlag": vessel["flag_country"] if vessel else None,
            "vesselType": vessel["ship_type_text"] if vessel else None,
            "vesselRiskTier": vessel["risk_tier"] if vessel else None,
            "encounterPartnerMmsi": r.get("encounter_mmsi"),
            "encounterPartnerName": partner["ship_name"] if partner else None,
            "encounterPartnerFlag": partner["flag_country"] if partner else None,
            "portName": r.get("port_name"),
            "durationHours": duration_hours,
        })

    return items
