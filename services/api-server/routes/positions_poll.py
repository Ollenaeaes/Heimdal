"""Polling endpoint for vessel positions — replaces WebSocket push.

Provides GET /api/vessels/positions?since=<ISO timestamp> to fetch
positions newer than the given time.  Frontend polls this every 30-60s.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import text

from shared.db.connection import get_session

router = APIRouter(prefix="/api/vessels", tags=["positions"])


@router.get("/positions")
async def get_recent_positions(
    since: str | None = Query(
        None,
        description="ISO 8601 timestamp. Returns positions newer than this. Defaults to last 5 minutes.",
    ),
    limit: int = Query(10000, ge=1, le=50000, description="Max positions to return"),
):
    """Fetch recent vessel positions for polling.

    Returns the latest position per vessel since the given timestamp,
    along with risk tier and score from the vessel profile.
    """
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            since_dt = datetime.now(timezone.utc) - timedelta(minutes=5)
    else:
        since_dt = datetime.now(timezone.utc) - timedelta(minutes=5)

    session_factory = get_session()
    async with session_factory() as session:
        # Use vessel_profiles.updated_at to catch batch-loaded data
        # (batch pipeline updates updated_at when loading positions,
        # while pos.timestamp reflects the original AIS timestamp)
        result = await session.execute(
            text("""
                SELECT vp.mmsi,
                       vp.last_lat AS lat,
                       vp.last_lon AS lon,
                       vp.last_sog AS sog,
                       vp.last_cog AS cog,
                       vp.last_heading AS heading,
                       vp.last_position_time AS timestamp,
                       vp.risk_tier,
                       vp.risk_score,
                       vp.ship_name,
                       vp.ship_type,
                       vp.length,
                       vp.width
                FROM vessel_profiles vp
                WHERE vp.updated_at > :since
                  AND vp.last_lat IS NOT NULL
                  AND vp.last_lon IS NOT NULL
                LIMIT :limit
            """),
            {"since": since_dt, "limit": limit},
        )
        rows = result.fetchall()

    positions = []
    for row in rows:
        positions.append({
            "mmsi": row[0],
            "lat": row[1],
            "lon": row[2],
            "sog": row[3],
            "cog": row[4],
            "heading": row[5],
            "nav_status": None,
            "timestamp": row[6].isoformat() if row[6] else None,
            "risk_tier": row[7] or "green",
            "risk_score": row[8] or 0,
            "ship_name": row[9],
            "ship_type": row[10],
            "length": row[11],
            "width": row[12],
        })

    return {
        "positions": positions,
        "count": len(positions),
        "server_time": datetime.now(timezone.utc).isoformat(),
    }
