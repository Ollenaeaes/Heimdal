"""Watchlist endpoints for the Heimdal API server.

Provides:
- GET    /api/watchlist          — list all watchlisted vessels
- POST   /api/watchlist/{mmsi}   — add a vessel to the watchlist
- DELETE /api/watchlist/{mmsi}   — remove a vessel from the watchlist
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from shared.db.connection import get_session

logger = logging.getLogger("api-server.watchlist")

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistAddBody(BaseModel):
    """Request body for adding a vessel to the watchlist."""

    reason: str | None = Field(None, description="Optional reason/notes for watchlisting")


@router.get("")
async def list_watchlist():
    """Return all watchlisted vessels with their notes."""
    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(
            text(
                "SELECT w.mmsi, w.reason, w.added_at, "
                "vp.ship_name, vp.flag_country, vp.risk_tier "
                "FROM watchlist w "
                "LEFT JOIN vessel_profiles vp ON w.mmsi = vp.mmsi "
                "ORDER BY w.added_at DESC"
            )
        )
        rows = [dict(r) for r in result.mappings().all()]
    return {"items": rows, "total": len(rows)}


@router.post("/{mmsi}", status_code=201)
async def add_to_watchlist(mmsi: int, body: WatchlistAddBody | None = None):
    """Add a vessel to the watchlist.

    The vessel must exist in vessel_profiles. If the vessel is already
    on the watchlist, the reason is updated (idempotent upsert).
    """
    reason = body.reason if body else None

    session_factory = get_session()
    async with session_factory() as session:
        # Check vessel exists
        result = await session.execute(
            text("SELECT mmsi FROM vessel_profiles WHERE mmsi = :mmsi"),
            {"mmsi": mmsi},
        )
        if not result.first():
            raise HTTPException(status_code=404, detail=f"Vessel {mmsi} not found in vessel_profiles")

        # Upsert into watchlist
        await session.execute(
            text(
                "INSERT INTO watchlist (mmsi, reason) "
                "VALUES (:mmsi, :reason) "
                "ON CONFLICT (mmsi) DO UPDATE SET reason = :reason, added_at = NOW()"
            ),
            {"mmsi": mmsi, "reason": reason},
        )
        await session.commit()

    return {"mmsi": mmsi, "reason": reason, "status": "added"}


@router.delete("/{mmsi}", status_code=200)
async def remove_from_watchlist(mmsi: int):
    """Remove a vessel from the watchlist."""
    session_factory = get_session()
    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM watchlist WHERE mmsi = :mmsi"),
            {"mmsi": mmsi},
        )
        await session.commit()

    return {"mmsi": mmsi, "status": "removed"}
