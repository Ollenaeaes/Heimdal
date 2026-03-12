"""Anomaly events REST endpoint.

Provides:
- GET /api/anomalies — paginated anomaly feed with filters (severity,
  time range, bbox, resolved status) and joined vessel name + risk tier.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import text

from shared.db.connection import get_session

logger = logging.getLogger("api-server.anomalies")

router = APIRouter(prefix="/api", tags=["anomalies"])


@router.get("/anomalies")
async def list_anomalies(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=1000, description="Items per page"),
    severity: Optional[str] = Query(None, description="Filter by severity (low, moderate, high, critical)"),
    resolved: Optional[bool] = Query(None, description="Filter by resolved status"),
    rule_id: Optional[str] = Query(None, description="Filter by rule ID"),
    start: Optional[datetime] = Query(None, description="Start of time range (ISO 8601)"),
    end: Optional[datetime] = Query(None, description="End of time range (ISO 8601)"),
    bbox: Optional[str] = Query(None, description="Bounding box: sw_lat,sw_lon,ne_lat,ne_lon"),
):
    """Return paginated anomaly feed with optional filters.

    Each anomaly includes the full event data plus the vessel's ship_name
    and risk_tier from the vessel_profiles table.
    """
    clauses: list[str] = []
    params: dict = {}

    if severity is not None:
        clauses.append("a.severity = :severity")
        params["severity"] = severity

    if resolved is not None:
        clauses.append("a.resolved = :resolved")
        params["resolved"] = resolved

    if rule_id is not None:
        clauses.append("a.rule_id = :rule_id")
        params["rule_id"] = rule_id

    if start is not None:
        clauses.append("a.created_at >= :start")
        params["start"] = start

    if end is not None:
        clauses.append("a.created_at <= :end")
        params["end"] = end

    if bbox is not None:
        try:
            parts = [float(x.strip()) for x in bbox.split(",")]
            if len(parts) != 4:
                raise ValueError("bbox must have exactly 4 values")
            sw_lat, sw_lon, ne_lat, ne_lon = parts
            clauses.append(
                "v.last_lat IS NOT NULL AND v.last_lon IS NOT NULL "
                "AND v.last_lat >= :sw_lat AND v.last_lat <= :ne_lat "
                "AND v.last_lon >= :sw_lon AND v.last_lon <= :ne_lon"
            )
            params.update(sw_lat=sw_lat, sw_lon=sw_lon, ne_lat=ne_lat, ne_lon=ne_lon)
        except (ValueError, TypeError):
            logger.warning("Invalid bbox parameter: %s", bbox)
            return {"items": [], "total": 0, "page": page, "per_page": per_page}

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    offset = (page - 1) * per_page
    params["limit"] = per_page
    params["offset"] = offset

    session_factory = get_session()
    async with session_factory() as session:
        # Count total matching rows
        count_sql = text(
            f"SELECT COUNT(*) FROM anomaly_events a "
            f"LEFT JOIN vessel_profiles v ON a.mmsi = v.mmsi "
            f"{where}"
        )
        count_result = await session.execute(count_sql, params)
        total = count_result.scalar() or 0

        # Fetch page of results
        query_sql = text(
            f"SELECT a.id, a.mmsi, a.rule_id, a.severity, a.points, "
            f"a.details, a.resolved, a.created_at, "
            f"v.ship_name AS vessel_name, v.risk_tier "
            f"FROM anomaly_events a "
            f"LEFT JOIN vessel_profiles v ON a.mmsi = v.mmsi "
            f"{where} "
            f"ORDER BY a.created_at DESC "
            f"LIMIT :limit OFFSET :offset"
        )
        result = await session.execute(query_sql, params)
        rows = result.mappings().all()

    items = []
    for row in rows:
        item = dict(row)
        # Ensure created_at is serialised as ISO string
        if isinstance(item.get("created_at"), datetime):
            item["created_at"] = item["created_at"].isoformat()
        items.append(item)

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
    }
