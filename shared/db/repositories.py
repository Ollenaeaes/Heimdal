"""Repository functions for database CRUD operations.

All functions are async and use raw SQL via sqlalchemy.text() for
performance-critical operations (bulk inserts) and straightforward
queries for simple CRUD.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.connection import get_session


# ===================================================================
# Vessel Profiles
# ===================================================================


async def upsert_vessel_profile(session: AsyncSession, data: dict[str, Any]) -> None:
    """Upsert a vessel profile by MMSI (insert or update on conflict)."""
    await session.execute(
        text("""
            INSERT INTO vessel_profiles (
                mmsi, imo, ship_name, ship_type, ship_type_text,
                flag_country, call_sign, length, width, draught,
                destination, eta, last_position_time, last_lat, last_lon,
                risk_score, risk_tier, sanctions_status, pi_tier, pi_details,
                owner, operator, insurer, class_society, build_year,
                dwt, gross_tonnage, group_owner, registered_owner,
                technical_manager, updated_at
            ) VALUES (
                :mmsi, :imo, :ship_name, :ship_type, :ship_type_text,
                :flag_country, :call_sign, :length, :width, :draught,
                :destination, :eta, :last_position_time, :last_lat, :last_lon,
                :risk_score, :risk_tier, :sanctions_status, :pi_tier, :pi_details,
                :owner, :operator, :insurer, :class_society, :build_year,
                :dwt, :gross_tonnage, :group_owner, :registered_owner,
                :technical_manager, NOW()
            )
            ON CONFLICT (mmsi) DO UPDATE SET
                imo = COALESCE(EXCLUDED.imo, vessel_profiles.imo),
                ship_name = COALESCE(EXCLUDED.ship_name, vessel_profiles.ship_name),
                ship_type = COALESCE(EXCLUDED.ship_type, vessel_profiles.ship_type),
                ship_type_text = COALESCE(EXCLUDED.ship_type_text, vessel_profiles.ship_type_text),
                flag_country = COALESCE(EXCLUDED.flag_country, vessel_profiles.flag_country),
                call_sign = COALESCE(EXCLUDED.call_sign, vessel_profiles.call_sign),
                length = COALESCE(EXCLUDED.length, vessel_profiles.length),
                width = COALESCE(EXCLUDED.width, vessel_profiles.width),
                draught = COALESCE(EXCLUDED.draught, vessel_profiles.draught),
                destination = COALESCE(EXCLUDED.destination, vessel_profiles.destination),
                eta = COALESCE(EXCLUDED.eta, vessel_profiles.eta),
                last_position_time = COALESCE(EXCLUDED.last_position_time, vessel_profiles.last_position_time),
                last_lat = COALESCE(EXCLUDED.last_lat, vessel_profiles.last_lat),
                last_lon = COALESCE(EXCLUDED.last_lon, vessel_profiles.last_lon),
                risk_score = COALESCE(EXCLUDED.risk_score, vessel_profiles.risk_score),
                risk_tier = COALESCE(EXCLUDED.risk_tier, vessel_profiles.risk_tier),
                sanctions_status = COALESCE(EXCLUDED.sanctions_status, vessel_profiles.sanctions_status),
                pi_tier = COALESCE(EXCLUDED.pi_tier, vessel_profiles.pi_tier),
                pi_details = COALESCE(EXCLUDED.pi_details, vessel_profiles.pi_details),
                owner = COALESCE(EXCLUDED.owner, vessel_profiles.owner),
                operator = COALESCE(EXCLUDED.operator, vessel_profiles.operator),
                insurer = COALESCE(EXCLUDED.insurer, vessel_profiles.insurer),
                class_society = COALESCE(EXCLUDED.class_society, vessel_profiles.class_society),
                build_year = COALESCE(EXCLUDED.build_year, vessel_profiles.build_year),
                dwt = COALESCE(EXCLUDED.dwt, vessel_profiles.dwt),
                gross_tonnage = COALESCE(EXCLUDED.gross_tonnage, vessel_profiles.gross_tonnage),
                group_owner = COALESCE(EXCLUDED.group_owner, vessel_profiles.group_owner),
                registered_owner = COALESCE(EXCLUDED.registered_owner, vessel_profiles.registered_owner),
                technical_manager = COALESCE(EXCLUDED.technical_manager, vessel_profiles.technical_manager),
                updated_at = NOW()
        """),
        data,
    )


async def update_vessel_sanctions(
    session: AsyncSession, mmsi: int, sanctions_status: str
) -> None:
    """Update only the sanctions_status column for a vessel profile."""
    await session.execute(
        text(
            "UPDATE vessel_profiles "
            "SET sanctions_status = :sanctions_status, updated_at = NOW() "
            "WHERE mmsi = :mmsi"
        ),
        {"mmsi": mmsi, "sanctions_status": sanctions_status},
    )


async def get_vessel_profile_by_mmsi(
    session: AsyncSession, mmsi: int
) -> dict[str, Any] | None:
    """Fetch a single vessel profile by MMSI."""
    result = await session.execute(
        text("SELECT * FROM vessel_profiles WHERE mmsi = :mmsi"),
        {"mmsi": mmsi},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def list_vessel_profiles(
    session: AsyncSession,
    *,
    risk_tier: Optional[str] = None,
    flag_country: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List vessel profiles with optional filters."""
    clauses = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if risk_tier:
        clauses.append("risk_tier = :risk_tier")
        params["risk_tier"] = risk_tier
    if flag_country:
        clauses.append("flag_country = :flag_country")
        params["flag_country"] = flag_country

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    result = await session.execute(
        text(
            f"SELECT * FROM vessel_profiles {where} "
            f"ORDER BY risk_score DESC LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    return [dict(r) for r in result.mappings().all()]


# ===================================================================
# Vessel Positions
# ===================================================================


async def bulk_insert_positions(
    session: AsyncSession, positions: list[dict[str, Any]]
) -> int:
    """Bulk insert vessel positions. Returns number of rows inserted."""
    if not positions:
        return 0
    await session.execute(
        text("""
            INSERT INTO vessel_positions (timestamp, mmsi, position, sog, cog, heading, nav_status, rot, draught)
            VALUES (
                :timestamp, :mmsi,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                :sog, :cog, :heading, :nav_status, :rot, :draught
            )
        """),
        positions,
    )
    return len(positions)


async def get_vessel_track(
    session: AsyncSession,
    mmsi: int,
    start_time: datetime,
    end_time: datetime,
) -> list[dict[str, Any]]:
    """Get position track for a vessel within a time range."""
    result = await session.execute(
        text("""
            SELECT
                timestamp, mmsi,
                ST_Y(position::geometry) AS lat,
                ST_X(position::geometry) AS lon,
                sog, cog, heading, nav_status, rot, draught
            FROM vessel_positions
            WHERE mmsi = :mmsi
              AND timestamp BETWEEN :start_time AND :end_time
            ORDER BY timestamp ASC
        """),
        {"mmsi": mmsi, "start_time": start_time, "end_time": end_time},
    )
    return [dict(r) for r in result.mappings().all()]


# ===================================================================
# Anomaly Events
# ===================================================================


async def create_anomaly_event(
    session: AsyncSession, data: dict[str, Any]
) -> int:
    """Create an anomaly event. Returns the new event ID."""
    result = await session.execute(
        text("""
            INSERT INTO anomaly_events (mmsi, rule_id, severity, points, details)
            VALUES (:mmsi, :rule_id, :severity, :points, :details)
            RETURNING id
        """),
        data,
    )
    row = result.first()
    return row[0] if row else 0


async def end_anomaly_event(
    session: AsyncSession, anomaly_id: int
) -> None:
    """End an active anomaly event: set event_end, event_state='ended', resolved=true."""
    await session.execute(
        text(
            "UPDATE anomaly_events "
            "SET event_end = NOW(), event_state = 'ended', resolved = true "
            "WHERE id = :anomaly_id"
        ),
        {"anomaly_id": anomaly_id},
    )


async def list_active_anomalies_by_mmsi(
    session: AsyncSession, mmsi: int
) -> list[dict[str, Any]]:
    """List only active (non-ended) anomaly events for a given vessel."""
    result = await session.execute(
        text("""
            SELECT * FROM anomaly_events
            WHERE mmsi = :mmsi AND event_state = 'active'
            ORDER BY created_at DESC
        """),
        {"mmsi": mmsi},
    )
    return [dict(r) for r in result.mappings().all()]


async def count_ended_events(
    session: AsyncSession, mmsi: int, rule_id: str, decay_days: int = 30
) -> int:
    """Count ended anomaly events for a given vessel and rule within the decay window."""
    result = await session.execute(
        text("""
            SELECT COUNT(*) FROM anomaly_events
            WHERE mmsi = :mmsi AND rule_id = :rule_id
              AND event_state = 'ended'
              AND event_end >= NOW() - INTERVAL '1 day' * :decay_days
        """),
        {"mmsi": mmsi, "rule_id": rule_id, "decay_days": decay_days},
    )
    row = result.first()
    return row[0] if row else 0


async def list_anomaly_events_by_mmsi(
    session: AsyncSession, mmsi: int, *, limit: int = 50
) -> list[dict[str, Any]]:
    """List anomaly events for a given vessel."""
    result = await session.execute(
        text("""
            SELECT * FROM anomaly_events
            WHERE mmsi = :mmsi
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"mmsi": mmsi, "limit": limit},
    )
    return [dict(r) for r in result.mappings().all()]


async def list_anomaly_events(
    session: AsyncSession,
    *,
    rule_id: Optional[str] = None,
    severity: Optional[str] = None,
    resolved: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List anomaly events with optional filters."""
    clauses = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if rule_id:
        clauses.append("rule_id = :rule_id")
        params["rule_id"] = rule_id
    if severity:
        clauses.append("severity = :severity")
        params["severity"] = severity
    if resolved is not None:
        clauses.append("resolved = :resolved")
        params["resolved"] = resolved

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    result = await session.execute(
        text(
            f"SELECT * FROM anomaly_events {where} "
            f"ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    return [dict(r) for r in result.mappings().all()]


# ===================================================================
# Manual Enrichment
# ===================================================================


async def create_manual_enrichment(
    session: AsyncSession, data: dict[str, Any]
) -> int:
    """Create a manual enrichment record. Returns the new ID."""
    result = await session.execute(
        text("""
            INSERT INTO manual_enrichment (mmsi, analyst_notes, source, pi_tier, confidence, attachments)
            VALUES (:mmsi, :analyst_notes, :source, :pi_tier, :confidence, :attachments)
            RETURNING id
        """),
        data,
    )
    row = result.first()
    return row[0] if row else 0


async def get_manual_enrichment_by_mmsi(
    session: AsyncSession, mmsi: int
) -> list[dict[str, Any]]:
    """Get all manual enrichment records for a vessel."""
    result = await session.execute(
        text("""
            SELECT * FROM manual_enrichment
            WHERE mmsi = :mmsi
            ORDER BY created_at DESC
        """),
        {"mmsi": mmsi},
    )
    return [dict(r) for r in result.mappings().all()]


# ===================================================================
# GFW Events
# ===================================================================


async def bulk_upsert_gfw_events(
    session: AsyncSession, events: list[dict[str, Any]]
) -> int:
    """Bulk upsert GFW events by gfw_event_id. Returns count processed."""
    if not events:
        return 0
    for event in events:
        await session.execute(
            text("""
                INSERT INTO gfw_events (
                    gfw_event_id, event_type, mmsi, start_time, end_time,
                    lat, lon, details, encounter_mmsi, port_name
                ) VALUES (
                    :gfw_event_id, :event_type, :mmsi, :start_time, :end_time,
                    :lat, :lon, :details, :encounter_mmsi, :port_name
                )
                ON CONFLICT (gfw_event_id) DO UPDATE SET
                    event_type = EXCLUDED.event_type,
                    mmsi = EXCLUDED.mmsi,
                    start_time = EXCLUDED.start_time,
                    end_time = EXCLUDED.end_time,
                    lat = EXCLUDED.lat,
                    lon = EXCLUDED.lon,
                    details = EXCLUDED.details,
                    encounter_mmsi = EXCLUDED.encounter_mmsi,
                    port_name = EXCLUDED.port_name,
                    ingested_at = NOW()
            """),
            event,
        )
    return len(events)


async def list_gfw_events_by_mmsi(
    session: AsyncSession, mmsi: int, *, limit: int = 50
) -> list[dict[str, Any]]:
    """List GFW events for a given vessel."""
    result = await session.execute(
        text("""
            SELECT * FROM gfw_events
            WHERE mmsi = :mmsi
            ORDER BY start_time DESC
            LIMIT :limit
        """),
        {"mmsi": mmsi, "limit": limit},
    )
    return [dict(r) for r in result.mappings().all()]


async def list_gfw_events(
    session: AsyncSession,
    *,
    event_type: Optional[str] = None,
    mmsi: Optional[int] = None,
    start_after: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List GFW events with optional filters."""
    clauses = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if event_type:
        clauses.append("event_type = :event_type")
        params["event_type"] = event_type
    if mmsi:
        clauses.append("mmsi = :mmsi")
        params["mmsi"] = mmsi
    if start_after:
        clauses.append("start_time >= :start_after")
        params["start_after"] = start_after

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    result = await session.execute(
        text(
            f"SELECT * FROM gfw_events {where} "
            f"ORDER BY start_time DESC LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    return [dict(r) for r in result.mappings().all()]


# ===================================================================
# SAR Detections
# ===================================================================


async def bulk_upsert_sar_detections(
    session: AsyncSession, detections: list[dict[str, Any]]
) -> int:
    """Bulk upsert SAR detections by gfw_detection_id. Returns count processed."""
    if not detections:
        return 0
    for det in detections:
        await session.execute(
            text("""
                INSERT INTO sar_detections (
                    detection_time, position, length_m, width_m, heading_deg,
                    confidence, is_dark, matched_mmsi, matched_category,
                    match_distance_m,
                    source, gfw_detection_id, matching_score, fishing_score
                ) VALUES (
                    :detection_time,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    :length_m, :width_m, :heading_deg,
                    :confidence, :is_dark, :matched_mmsi, :matched_category,
                    :match_distance_m,
                    :source, :gfw_detection_id, :matching_score, :fishing_score
                )
                ON CONFLICT (gfw_detection_id) DO UPDATE SET
                    detection_time = EXCLUDED.detection_time,
                    position = EXCLUDED.position,
                    length_m = EXCLUDED.length_m,
                    width_m = EXCLUDED.width_m,
                    heading_deg = EXCLUDED.heading_deg,
                    confidence = EXCLUDED.confidence,
                    is_dark = EXCLUDED.is_dark,
                    matched_mmsi = EXCLUDED.matched_mmsi,
                    matched_category = EXCLUDED.matched_category,
                    match_distance_m = EXCLUDED.match_distance_m,
                    matching_score = EXCLUDED.matching_score,
                    fishing_score = EXCLUDED.fishing_score
            """),
            det,
        )
    return len(detections)


async def list_sar_detections(
    session: AsyncSession,
    *,
    is_dark: Optional[bool] = None,
    source: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List SAR detections with optional filters."""
    clauses = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if is_dark is not None:
        clauses.append("is_dark = :is_dark")
        params["is_dark"] = is_dark
    if source:
        clauses.append("source = :source")
        params["source"] = source

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    result = await session.execute(
        text(
            f"SELECT id, detection_time, "
            f"ST_Y(position::geometry) AS lat, ST_X(position::geometry) AS lon, "
            f"length_m, width_m, heading_deg, confidence, is_dark, "
            f"matched_mmsi, matched_category, match_distance_m, source, "
            f"gfw_detection_id, "
            f"matching_score, fishing_score, created_at "
            f"FROM sar_detections {where} "
            f"ORDER BY detection_time DESC LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    return [dict(r) for r in result.mappings().all()]
