"""Vessel REST endpoints for the Heimdal API server.

Provides:
- GET /api/vessels           — paginated vessel list with filters
- GET /api/vessels/{mmsi}    — full vessel profile
- GET /api/vessels/{mmsi}/track — vessel position track
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from shared.db.connection import get_session

logger = logging.getLogger("api-server.vessels")

router = APIRouter(prefix="/api", tags=["vessels"])

# Fields returned in the vessel summary (list endpoint)
_SUMMARY_FIELDS = (
    "mmsi, imo, ship_name, flag_country, ship_type, "
    "risk_tier, risk_score, last_lat, last_lon, "
    "last_position_time, sanctions_status"
)


@router.get("/vessels")
async def list_vessels(
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=1000),
    risk_tier: Optional[str] = Query(None),
    bbox: Optional[str] = Query(None, description="sw_lat,sw_lon,ne_lat,ne_lon"),
    ship_type: Optional[str] = Query(None, description="Comma-separated ship type codes"),
    sanctions_hit: Optional[bool] = Query(None),
    active_since: Optional[datetime] = Query(None),
):
    """Return paginated vessel list with optional filters."""
    clauses: list[str] = []
    params: dict = {}

    if risk_tier:
        clauses.append("risk_tier = :risk_tier")
        params["risk_tier"] = risk_tier

    if bbox:
        parts = bbox.split(",")
        if len(parts) != 4:
            raise HTTPException(status_code=400, detail="bbox must be sw_lat,sw_lon,ne_lat,ne_lon")
        try:
            sw_lat, sw_lon, ne_lat, ne_lon = (float(p) for p in parts)
        except ValueError:
            raise HTTPException(status_code=400, detail="bbox values must be numeric")
        clauses.append(
            "last_lat >= :sw_lat AND last_lat <= :ne_lat "
            "AND last_lon >= :sw_lon AND last_lon <= :ne_lon"
        )
        params.update(sw_lat=sw_lat, sw_lon=sw_lon, ne_lat=ne_lat, ne_lon=ne_lon)

    if ship_type:
        try:
            type_codes = [int(t.strip()) for t in ship_type.split(",")]
        except ValueError:
            raise HTTPException(status_code=400, detail="ship_type values must be integers")
        # Use ANY(:ship_types) for array matching
        clauses.append("ship_type = ANY(:ship_types)")
        params["ship_types"] = type_codes

    if sanctions_hit is True:
        clauses.append("sanctions_status IS NOT NULL AND sanctions_status != ''")

    if active_since:
        clauses.append("last_position_time >= :active_since")
        params["active_since"] = active_since

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    offset = (page - 1) * per_page

    session_factory = get_session()
    async with session_factory() as session:
        # Get total count
        count_result = await session.execute(
            text(f"SELECT COUNT(*) FROM vessel_profiles {where}"),
            params,
        )
        total = count_result.scalar() or 0

        # Get page of results
        result = await session.execute(
            text(
                f"SELECT {_SUMMARY_FIELDS} FROM vessel_profiles {where} "
                f"ORDER BY risk_score DESC NULLS LAST "
                f"LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": per_page, "offset": offset},
        )
        rows = result.mappings().all()

    items = []
    for row in rows:
        r = dict(row)
        items.append({
            "mmsi": r["mmsi"],
            "imo": r.get("imo"),
            "ship_name": r.get("ship_name"),
            "flag_state": r.get("flag_country"),
            "ship_type": r.get("ship_type"),
            "risk_tier": r.get("risk_tier"),
            "risk_score": r.get("risk_score"),
            "last_position": {
                "lat": r.get("last_lat"),
                "lon": r.get("last_lon"),
                "sog": None,
                "cog": None,
                "timestamp": r.get("last_position_time").isoformat()
                if r.get("last_position_time")
                else None,
            },
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/vessels/{mmsi}")
async def get_vessel(mmsi: int):
    """Return full vessel profile including last position, anomaly count, latest enrichment, sanctions details."""
    session_factory = get_session()
    async with session_factory() as session:
        # Fetch vessel profile
        result = await session.execute(
            text("SELECT * FROM vessel_profiles WHERE mmsi = :mmsi"),
            {"mmsi": mmsi},
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Vessel not found")

        profile = dict(row)

        # Active anomaly count
        anomaly_result = await session.execute(
            text(
                "SELECT COUNT(*) FROM anomaly_events "
                "WHERE mmsi = :mmsi AND resolved = false"
            ),
            {"mmsi": mmsi},
        )
        active_anomaly_count = anomaly_result.scalar() or 0

        # Latest manual enrichment
        enrichment_result = await session.execute(
            text(
                "SELECT * FROM manual_enrichment "
                "WHERE mmsi = :mmsi ORDER BY created_at DESC LIMIT 1"
            ),
            {"mmsi": mmsi},
        )
        enrichment_row = enrichment_result.mappings().first()
        latest_enrichment = dict(enrichment_row) if enrichment_row else None

    return {
        **profile,
        "last_position": {
            "lat": profile.get("last_lat"),
            "lon": profile.get("last_lon"),
            "sog": None,
            "cog": None,
            "timestamp": profile.get("last_position_time").isoformat()
            if profile.get("last_position_time")
            else None,
        },
        "active_anomaly_count": active_anomaly_count,
        "latest_enrichment": latest_enrichment,
    }


@router.get("/vessels/{mmsi}/track")
async def get_vessel_track(
    mmsi: int,
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    simplify: Optional[float] = Query(None, ge=0, description="ST_Simplify tolerance"),
):
    """Return vessel position track, chronologically ordered."""
    now = datetime.now(timezone.utc)
    if end is None:
        end = now
    if start is None:
        start = end - timedelta(hours=24)

    if simplify is not None and simplify > 0:
        select_clause = (
            "SELECT timestamp, "
            "ST_Y(ST_Simplify(position::geometry, :tolerance)) AS lat, "
            "ST_X(ST_Simplify(position::geometry, :tolerance)) AS lon, "
            "sog, cog, draught"
        )
    else:
        select_clause = (
            "SELECT timestamp, "
            "ST_Y(position::geometry) AS lat, "
            "ST_X(position::geometry) AS lon, "
            "sog, cog, draught"
        )

    sql = (
        f"{select_clause} "
        f"FROM vessel_positions "
        f"WHERE mmsi = :mmsi AND timestamp BETWEEN :start_time AND :end_time "
        f"ORDER BY timestamp ASC"
    )

    params: dict = {"mmsi": mmsi, "start_time": start, "end_time": end}
    if simplify is not None and simplify > 0:
        params["tolerance"] = simplify

    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(text(sql), params)
        rows = result.mappings().all()

    return [dict(r) for r in rows]
