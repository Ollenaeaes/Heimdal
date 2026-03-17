"""Vessel REST endpoints for the Heimdal API server.

Provides:
- GET /api/vessels              — paginated vessel list with filters
- GET /api/vessels/snapshot     — lightweight map snapshot
- GET /api/vessels/area-history — historical vessels within a polygon
- GET /api/vessels/{mmsi}       — full vessel profile
- GET /api/vessels/{mmsi}/track — vessel position track
- GET /api/vessels/{mmsi}/track/export — track export (JSON/CSV, with cold storage)
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import json as _json

import pyarrow.parquet as pq
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import text

from shared.config import get_settings
from shared.db.connection import get_session

logger = logging.getLogger("api-server.vessels")

router = APIRouter(prefix="/api", tags=["vessels"])

# Limit concurrent Parquet export reads
_export_semaphore = asyncio.Semaphore(2)

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


@router.get("/vessels/snapshot")
async def vessel_snapshot(
    risk_tiers: Optional[str] = Query(None, description="Comma-separated risk tiers to include"),
    bbox: Optional[str] = Query(None, description="sw_lat,sw_lon,ne_lat,ne_lon"),
    sample: int = Query(1, ge=1, le=20, description="Show every Nth vessel (deterministic thinning via mmsi modulo)"),
):
    """Return a lightweight snapshot of vessels for map seeding.

    Returns minimal fields (mmsi, lat, lon, risk_tier, risk_score,
    ship_type, cog, sog) so the frontend can render the globe without
    waiting for WebSocket data.

    Supports filtering by risk_tiers and bounding box so the frontend
    can load high-risk vessels globally and green vessels only within
    the current viewport. The sample parameter thins results at zoom-out
    levels (e.g. sample=5 returns every 5th vessel by MMSI).
    """
    clauses: list[str] = ["vp.last_lat IS NOT NULL AND vp.last_lon IS NOT NULL"]
    params: dict = {}

    if risk_tiers:
        tiers = [t.strip() for t in risk_tiers.split(",") if t.strip()]
        clauses.append("vp.risk_tier = ANY(:risk_tiers)")
        params["risk_tiers"] = tiers

    if sample > 1:
        clauses.append("MOD(ABS(hashint4(vp.mmsi)), :sample) = 0")
        params["sample"] = sample

    if bbox:
        parts = bbox.split(",")
        if len(parts) == 4:
            try:
                sw_lat, sw_lon, ne_lat, ne_lon = (float(p) for p in parts)
                clauses.append(
                    "vp.last_lat >= :sw_lat AND vp.last_lat <= :ne_lat "
                    "AND vp.last_lon >= :sw_lon AND vp.last_lon <= :ne_lon"
                )
                params.update(sw_lat=sw_lat, sw_lon=sw_lon, ne_lat=ne_lat, ne_lon=ne_lon)
            except ValueError:
                pass

    where = f"WHERE {' AND '.join(clauses)}"

    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(
            text(
                f"SELECT vp.mmsi, vp.last_lat, vp.last_lon, vp.risk_tier, "
                f"vp.risk_score, vp.ship_type, vp.ship_name, "
                f"lp.cog, lp.sog "
                f"FROM vessel_profiles vp "
                f"LEFT JOIN LATERAL ("
                f"  SELECT cog, sog FROM vessel_positions "
                f"  WHERE mmsi = vp.mmsi "
                f"  ORDER BY timestamp DESC LIMIT 1"
                f") lp ON true "
                f"{where}"
            ),
            params,
        )
        rows = result.mappings().all()

    return [
        {
            "mmsi": r["mmsi"],
            "lat": r["last_lat"],
            "lon": r["last_lon"],
            "risk_tier": r["risk_tier"] or "green",
            "risk_score": r["risk_score"] or 0,
            "ship_type": r.get("ship_type"),
            "name": r.get("ship_name"),
            "cog": r.get("cog"),
            "sog": r.get("sog"),
        }
        for r in rows
    ]


@router.get("/vessels/area-history")
async def area_history(
    polygon: str = Query(..., description="JSON array of [lon, lat] coordinate pairs"),
    start: datetime = Query(...),
    end: datetime = Query(...),
):
    """Return vessels that appeared within a polygon during a time range."""
    # Parse polygon JSON
    try:
        coords = _json.loads(polygon)
    except _json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="polygon must be valid JSON")

    if not isinstance(coords, list) or len(coords) < 3:
        raise HTTPException(
            status_code=400,
            detail="polygon must have at least 3 coordinate pairs",
        )

    for i, pair in enumerate(coords):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise HTTPException(
                status_code=400,
                detail=f"coordinate at index {i} must be a [lon, lat] pair",
            )

    # Close the ring if not already closed
    if coords[0] != coords[-1]:
        coords.append(coords[0])

    # Clamp date range to max 30 days
    max_range = timedelta(days=30)
    if end - start > max_range:
        start = end - max_range

    # Build GeoJSON polygon
    geojson_polygon = _json.dumps({
        "type": "Polygon",
        "coordinates": [coords],
    })

    sql = text(
        "SELECT vp.mmsi, vp2.ship_name, vp2.flag_country, vp2.risk_tier, "
        "COUNT(*) as position_count "
        "FROM vessel_positions vp "
        "JOIN vessel_profiles vp2 ON vp.mmsi = vp2.mmsi "
        "WHERE vp.timestamp BETWEEN :start AND :end "
        "  AND ST_Within(vp.position::geometry, ST_GeomFromGeoJSON(:polygon_geojson)) "
        "GROUP BY vp.mmsi, vp2.ship_name, vp2.flag_country, vp2.risk_tier "
        "ORDER BY position_count DESC "
        "LIMIT 50"
    )

    session_factory = get_session()
    async with session_factory() as session:
        result = await session.execute(sql, {
            "start": start,
            "end": end,
            "polygon_geojson": geojson_polygon,
        })
        rows = result.mappings().all()

    return [
        {
            "mmsi": r["mmsi"],
            "ship_name": r["ship_name"],
            "flag_state": r["flag_country"],
            "risk_tier": r["risk_tier"],
            "position_count": r["position_count"],
        }
        for r in rows
    ]


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

        # Active anomalies (full data for UI breakdown)
        anomaly_result = await session.execute(
            text(
                "SELECT id, rule_id, severity, points, details, created_at "
                "FROM anomaly_events "
                "WHERE mmsi = :mmsi AND resolved = false "
                "ORDER BY points DESC, created_at DESC "
                "LIMIT 50"
            ),
            {"mmsi": mmsi},
        )
        anomaly_rows = anomaly_result.mappings().all()
        anomalies = [
            {
                "id": r["id"],
                "ruleId": r["rule_id"],
                "severity": r["severity"],
                "points": float(r["points"]),
                "details": _json.loads(r["details"]) if isinstance(r["details"], str) else (r["details"] or {}),
                "timestamp": r["created_at"].isoformat() if r["created_at"] else None,
                "resolved": False,
            }
            for r in anomaly_rows
        ]
        active_anomaly_count = len(anomalies)

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

        # Latest position (for sog, cog, heading, nav_status, draught)
        pos_result = await session.execute(
            text(
                "SELECT sog, cog, heading, nav_status, draught, timestamp "
                "FROM vessel_positions "
                "WHERE mmsi = :mmsi ORDER BY timestamp DESC LIMIT 1"
            ),
            {"mmsi": mmsi},
        )
        pos_row = pos_result.mappings().first()
        last_pos = dict(pos_row) if pos_row else {}

        # Equasis data
        equasis_latest_result = await session.execute(
            text(
                "SELECT * FROM equasis_data "
                "WHERE mmsi = :mmsi ORDER BY upload_timestamp DESC LIMIT 1"
            ),
            {"mmsi": mmsi},
        )
        equasis_latest_row = equasis_latest_result.mappings().first()

        equasis_count_result = await session.execute(
            text("SELECT COUNT(*) FROM equasis_data WHERE mmsi = :mmsi"),
            {"mmsi": mmsi},
        )
        equasis_count = equasis_count_result.scalar() or 0

        equasis_uploads_result = await session.execute(
            text(
                "SELECT id, upload_timestamp, edition_date "
                "FROM equasis_data WHERE mmsi = :mmsi "
                "ORDER BY upload_timestamp DESC"
            ),
            {"mmsi": mmsi},
        )
        equasis_uploads = [dict(r) for r in equasis_uploads_result.mappings().all()]

    return {
        **profile,
        "last_position": {
            "lat": profile.get("last_lat"),
            "lon": profile.get("last_lon"),
            "sog": last_pos.get("sog"),
            "cog": last_pos.get("cog"),
            "heading": last_pos.get("heading"),
            "nav_status": last_pos.get("nav_status"),
            "draught": round(float(d), 1) if (d := last_pos.get("draught") or profile.get("draught")) is not None else None,
            "timestamp": profile.get("last_position_time").isoformat()
            if profile.get("last_position_time")
            else None,
        },
        "active_anomaly_count": active_anomaly_count,
        "anomalies": anomalies,
        "latest_enrichment": latest_enrichment,
        "equasis": {
            "latest": dict(equasis_latest_row) if equasis_latest_row else None,
            "upload_count": equasis_count,
            "uploads": equasis_uploads,
        } if equasis_latest_row else None,
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


@router.get("/vessels/{mmsi}/track/export")
async def export_vessel_track(
    mmsi: int,
    start: datetime = Query(...),
    end: datetime = Query(...),
    format: str = Query("json", pattern="^(json|csv)$"),
):
    """Export vessel track data as JSON or CSV, reading from cold Parquet storage for older data."""
    settings = get_settings()
    base_path = Path(settings.raw_storage.base_path)
    cold_age = timedelta(days=30)
    now = datetime.now(timezone.utc)
    cutoff = now - cold_age

    positions: list[dict] = []

    # --- Portion within last 30 days: query the DB ---
    db_start = max(start, cutoff)
    db_end = end
    if db_end > db_start:
        session_factory = get_session()
        async with session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT timestamp, "
                    "ST_Y(position::geometry) AS lat, "
                    "ST_X(position::geometry) AS lon, "
                    "sog, cog, heading "
                    "FROM vessel_positions "
                    "WHERE mmsi = :mmsi AND timestamp BETWEEN :start_time AND :end_time "
                    "ORDER BY timestamp ASC"
                ),
                {"mmsi": mmsi, "start_time": db_start, "end_time": db_end},
            )
            for r in result.mappings().all():
                positions.append({
                    "timestamp": r["timestamp"].isoformat() if r["timestamp"] else None,
                    "lat": r["lat"],
                    "lon": r["lon"],
                    "sog": r["sog"],
                    "cog": r["cog"],
                    "heading": r["heading"],
                })

    # --- Portion older than 30 days: read from cold Parquet storage ---
    parquet_end = min(end, cutoff)
    if start < parquet_end:
        async with _export_semaphore:
            parquet_positions = await asyncio.to_thread(
                _read_parquet_positions, base_path, mmsi, start, parquet_end
            )
        positions = parquet_positions + positions  # prepend older data

    # --- Format output ---
    if format == "csv":
        return _build_csv_response(positions, mmsi, start, end)

    return positions


def _read_parquet_positions(
    base_path: Path,
    mmsi: int,
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Read positions from monthly Parquet files in cold storage."""
    positions: list[dict] = []

    # Iterate over each month in the range
    current = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while current <= end:
        year = current.year
        month = current.month
        # Build path from validated date components only (no user input)
        parquet_path = (
            base_path
            / "cold"
            / "ais"
            / f"{year:04d}"
            / f"{month:02d}"
            / f"positions_{year:04d}-{month:02d}.parquet"
        )

        if parquet_path.exists():
            try:
                table = pq.read_table(
                    str(parquet_path),
                    filters=[("mmsi", "=", mmsi)],
                )
                df = table.to_pandas()

                if not df.empty:
                    # Filter by timestamp range
                    if "timestamp" in df.columns:
                        ts = df["timestamp"]
                        mask = (ts >= start) & (ts <= end)
                        df = df[mask]

                    for _, row in df.iterrows():
                        ts_val = row.get("timestamp")
                        positions.append({
                            "timestamp": ts_val.isoformat() if hasattr(ts_val, "isoformat") else str(ts_val),
                            "lat": row.get("lat"),
                            "lon": row.get("lon"),
                            "sog": row.get("sog"),
                            "cog": row.get("cog"),
                            "heading": row.get("heading"),
                        })
            except Exception:
                logger.warning("Failed to read parquet file %s", parquet_path, exc_info=True)

        # Advance to next month
        if month == 12:
            current = current.replace(year=year + 1, month=1)
        else:
            current = current.replace(month=month + 1)

    # Sort by timestamp
    positions.sort(key=lambda p: p["timestamp"] or "")
    return positions


def _build_csv_response(
    positions: list[dict], mmsi: int, start: datetime, end: datetime
) -> Response:
    """Build a CSV file response from position data."""
    output = io.StringIO()
    fieldnames = ["timestamp", "lat", "lon", "sog", "cog", "heading"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for pos in positions:
        writer.writerow(pos)

    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")
    filename = f"track-{mmsi}-{start_str}-{end_str}.csv"

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
