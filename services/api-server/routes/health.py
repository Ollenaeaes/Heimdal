"""Health and stats endpoints for the Heimdal API server.

Provides:
- GET /api/health — system health check (DB, Redis, AIS websocket state)
- GET /api/stats  — platform statistics (vessels, anomalies, ingestion)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from shared.db.connection import get_session

logger = logging.getLogger("api-server.health")

router = APIRouter(prefix="/api", tags=["health"])

# Redis metric keys published by ais-ingest
_RATE_KEY = "heimdal:metrics:ingest_rate"
_LAST_MESSAGE_KEY = "heimdal:metrics:last_message_at"
_VESSELS_KEY = "heimdal:metrics:total_vessels"


@router.get("/health")
async def health(request: Request, response: Response):
    """System health check.

    Returns connectivity status for database and Redis, AIS websocket
    state inferred from Redis metrics, and summary counts.
    """
    redis = request.app.state.redis

    # --- Database check ---
    db_ok = False
    try:
        session_factory = get_session()
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        logger.warning("Database health check failed", exc_info=True)

    # --- Redis check ---
    redis_ok = False
    try:
        pong = await redis.ping()
        redis_ok = bool(pong)
    except Exception:
        logger.warning("Redis health check failed", exc_info=True)

    # --- AIS websocket state (inferred from last_message_at) ---
    last_position_ts: str | None = None
    ais_connected = False
    try:
        last_position_ts = await redis.get(_LAST_MESSAGE_KEY)
        if last_position_ts:
            last_dt = datetime.fromisoformat(last_position_ts)
            age_seconds = (datetime.now(timezone.utc) - last_dt).total_seconds()
            # Consider AIS connected if we received a message in the last 120s
            ais_connected = age_seconds < 120
    except Exception:
        logger.warning("Failed to read AIS metrics from Redis", exc_info=True)

    # --- Vessel & anomaly counts from DB ---
    vessel_count = 0
    anomaly_count = 0
    if db_ok:
        try:
            async with session_factory() as session:
                result = await session.execute(
                    text("SELECT COUNT(*) FROM vessel_profiles")
                )
                vessel_count = result.scalar() or 0

                result = await session.execute(
                    text("SELECT COUNT(*) FROM anomaly_events WHERE resolved = false")
                )
                anomaly_count = result.scalar() or 0
        except Exception:
            logger.warning("Failed to read counts for health endpoint", exc_info=True)

    # --- Determine overall status ---
    all_healthy = db_ok and redis_ok
    if not all_healthy:
        response.status_code = 503

    return {
        "status": "ok" if all_healthy else "degraded",
        "database": db_ok,
        "redis": redis_ok,
        "ais_connected": ais_connected,
        "last_position_timestamp": last_position_ts,
        "vessel_count": vessel_count,
        "anomaly_count": anomaly_count,
    }


@router.get("/stats")
async def stats(request: Request):
    """Platform statistics: vessels by tier, anomalies by severity, ingestion rate."""
    redis = request.app.state.redis
    session_factory = get_session()

    # --- Vessel counts by risk tier ---
    tier_counts = {"green": 0, "yellow": 0, "red": 0}
    total_vessels = 0
    try:
        async with session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT risk_tier, COUNT(*) AS cnt "
                    "FROM vessel_profiles "
                    "GROUP BY risk_tier"
                )
            )
            for row in result.mappings().all():
                tier = row["risk_tier"]
                cnt = row["cnt"]
                if tier in tier_counts:
                    tier_counts[tier] = cnt
                total_vessels += cnt
    except Exception:
        logger.warning("Failed to query vessel tier counts", exc_info=True)

    # --- Active anomalies by severity ---
    anomalies_by_severity: dict[str, int] = {}
    try:
        async with session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT severity, COUNT(*) AS cnt "
                    "FROM anomaly_events "
                    "WHERE resolved = false "
                    "GROUP BY severity"
                )
            )
            for row in result.mappings().all():
                anomalies_by_severity[row["severity"]] = row["cnt"]
    except Exception:
        logger.warning("Failed to query anomaly severity counts", exc_info=True)

    # --- Dark ship candidate count ---
    dark_ship_count = 0
    try:
        async with session_factory() as session:
            result = await session.execute(
                text("SELECT COUNT(*) FROM sar_detections WHERE is_dark = true")
            )
            dark_ship_count = result.scalar() or 0
    except Exception:
        logger.warning("Failed to query dark ship count", exc_info=True)

    # --- Ingestion metrics from Redis ---
    ingest_rate: float | None = None
    try:
        raw_rate = await redis.get(_RATE_KEY)
        if raw_rate is not None:
            ingest_rate = float(raw_rate)
    except Exception:
        logger.warning("Failed to read ingestion rate from Redis", exc_info=True)

    # --- Storage usage estimate (row counts as proxy) ---
    _STORAGE_QUERIES = {
        "vessel_positions": text("SELECT COUNT(*) FROM vessel_positions"),
        "vessel_profiles": text("SELECT COUNT(*) FROM vessel_profiles"),
        "anomaly_events": text("SELECT COUNT(*) FROM anomaly_events"),
        "sar_detections": text("SELECT COUNT(*) FROM sar_detections"),
    }
    storage_estimate: dict[str, int] = {}
    try:
        async with session_factory() as session:
            for table_name, query in _STORAGE_QUERIES.items():
                result = await session.execute(query)
                storage_estimate[table_name] = result.scalar() or 0
    except Exception:
        logger.warning("Failed to estimate storage usage", exc_info=True)

    return {
        "total_vessels": total_vessels,
        "vessels_by_risk_tier": tier_counts,
        "active_anomalies_by_severity": anomalies_by_severity,
        "dark_ship_candidates": dark_ship_count,
        "ingestion_rate": ingest_rate,
        "storage_estimate": storage_estimate,
    }
