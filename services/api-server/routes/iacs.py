"""IACS Classification Status endpoints.

Provides:
- GET /api/iacs/vessel/{imo}     — IACS class status for a single vessel
- GET /api/iacs/risk-vessels     — all vessels with Withdrawn/Suspended class
- GET /api/iacs/recent-changes   — changes detected in last N days
- GET /api/iacs/snapshots        — import history
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import text

from shared.db.connection import get_session

logger = logging.getLogger("api-server.iacs")

router = APIRouter(prefix="/api/iacs", tags=["iacs"])


@router.get("/vessel/{imo}")
async def get_vessel_iacs_status(imo: int):
    """Return IACS classification status for a single vessel."""
    session_factory = get_session()
    async with session_factory() as session:
        # Current state
        result = await session.execute(
            text("SELECT * FROM iacs_vessels_current WHERE imo = :imo"),
            {"imo": imo},
        )
        current = result.mappings().first()

        # Recent changes
        changes_result = await session.execute(
            text("""
                SELECT change_type, field_changed, old_value, new_value,
                       is_high_risk, detected_at, snapshot_date
                FROM iacs_vessels_changes
                WHERE imo = :imo
                ORDER BY detected_at DESC
                LIMIT 20
            """),
            {"imo": imo},
        )
        changes = [dict(r) for r in changes_result.mappings().all()]

    if not current:
        return {
            "imo": imo,
            "status": "NO_IACS_CLASS",
            "risk_signal": "moderate",
            "class_society": None,
            "reason": "Vessel not found in any IACS classification society records",
            "changes": [],
        }

    current = dict(current)
    status = current.get("status", "")
    reason = current.get("reason", "")

    if status == "Withdrawn":
        risk_signal = "critical" if "by society" in reason.lower() else "high"
    elif status in ("Suspended", "Removed"):
        risk_signal = "high"
    elif status in ("Delivered", "Reinstated"):
        risk_signal = "none"
    else:
        risk_signal = "low"

    return {
        "imo": imo,
        "status": status,
        "risk_signal": risk_signal,
        "class_society": current.get("class_society"),
        "reason": reason,
        "ship_name": current.get("ship_name"),
        "date_of_survey": current.get("date_of_survey"),
        "date_of_next_survey": current.get("date_of_next_survey"),
        "date_of_latest_status": current.get("date_of_latest_status"),
        "last_seen": current.get("last_seen"),
        "snapshot_date": current.get("snapshot_date"),
        "all_entries": current.get("all_entries"),
        "changes": changes,
    }


@router.get("/risk-vessels")
async def list_risk_vessels(
    status: Optional[str] = Query(None, description="Filter by status (Withdrawn, Suspended, Removed)"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    """Return all vessels with Withdrawn, Suspended, or Removed IACS class status."""
    session_factory = get_session()
    async with session_factory() as session:
        conditions = ["status IN ('Withdrawn', 'Suspended', 'Removed')"]
        params: dict = {"limit": limit, "offset": offset}

        if status:
            conditions = ["status = :status"]
            params["status"] = status

        where = " AND ".join(conditions)
        result = await session.execute(
            text(f"""
                SELECT imo, ship_name, class_society, status, reason,
                       date_of_latest_status, last_seen, snapshot_date
                FROM iacs_vessels_current
                WHERE {where}
                ORDER BY date_of_latest_status DESC NULLS LAST
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
        rows = [dict(r) for r in result.mappings().all()]

        count_result = await session.execute(
            text(f"SELECT COUNT(*) FROM iacs_vessels_current WHERE {where}"),
            params,
        )
        total = count_result.scalar()

    return {"items": rows, "total": total}


@router.get("/recent-changes")
async def list_recent_changes(
    days: int = Query(7, ge=1, le=90),
    high_risk_only: bool = Query(False),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    """Return IACS changes detected in the last N days."""
    session_factory = get_session()
    async with session_factory() as session:
        conditions = ["detected_at >= NOW() - make_interval(days => :days)"]
        params: dict = {"days": days, "limit": limit, "offset": offset}

        if high_risk_only:
            conditions.append("is_high_risk = TRUE")

        where = " AND ".join(conditions)
        result = await session.execute(
            text(f"""
                SELECT imo, ship_name, change_type, field_changed,
                       old_value, new_value, is_high_risk, detected_at, snapshot_date
                FROM iacs_vessels_changes
                WHERE {where}
                ORDER BY is_high_risk DESC, detected_at DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
        rows = [dict(r) for r in result.mappings().all()]

        count_result = await session.execute(
            text(f"SELECT COUNT(*) FROM iacs_vessels_changes WHERE {where}"),
            params,
        )
        total = count_result.scalar()

    return {"items": rows, "total": total}


@router.get("/snapshots")
async def list_snapshots():
    """Return IACS import history."""
    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(
            text("""
                SELECT id, filename, snapshot_date, row_count,
                       vessels_added, vessels_changed, vessels_removed, imported_at
                FROM iacs_snapshots
                ORDER BY snapshot_date DESC
            """)
        )
        rows = [dict(r) for r in result.mappings().all()]

    return {"items": rows, "total": len(rows)}
