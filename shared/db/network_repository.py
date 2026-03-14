"""Repository functions for network edge CRUD operations.

Provides async functions for managing vessel-to-vessel network edges
used in sanctions evasion network mapping.  All functions use raw SQL
via sqlalchemy.text() matching the pattern in repositories.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _normalize_mmsi_pair(mmsi_a: int, mmsi_b: int) -> tuple[int, int]:
    """Normalize MMSI pair so vessel_a_mmsi < vessel_b_mmsi."""
    return (min(mmsi_a, mmsi_b), max(mmsi_a, mmsi_b))


async def upsert_network_edge(
    session: AsyncSession,
    mmsi_a: int,
    mmsi_b: int,
    edge_type: str,
    confidence: float = 1.0,
    location: Optional[dict[str, float]] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Insert or update a network edge between two vessels.

    MMSI order is normalized (min as vessel_a) so that (A, B) and (B, A)
    map to the same row.  On conflict the observation_count is incremented,
    last_observed is updated, and confidence is set to the maximum.
    """
    vessel_a, vessel_b = _normalize_mmsi_pair(mmsi_a, mmsi_b)

    if location:
        location_expr = "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography"
        params: dict[str, Any] = {
            "vessel_a": vessel_a,
            "vessel_b": vessel_b,
            "edge_type": edge_type,
            "confidence": confidence,
            "lat": location["lat"],
            "lon": location["lon"],
            "details": details or {},
        }
    else:
        location_expr = "NULL"
        params = {
            "vessel_a": vessel_a,
            "vessel_b": vessel_b,
            "edge_type": edge_type,
            "confidence": confidence,
            "details": details or {},
        }

    await session.execute(
        text(f"""
            INSERT INTO network_edges (
                vessel_a_mmsi, vessel_b_mmsi, edge_type, confidence,
                first_observed, last_observed, observation_count,
                location, details
            ) VALUES (
                :vessel_a, :vessel_b, :edge_type, :confidence,
                NOW(), NOW(), 1,
                {location_expr}, :details
            )
            ON CONFLICT (vessel_a_mmsi, vessel_b_mmsi, edge_type) DO UPDATE SET
                last_observed = NOW(),
                observation_count = network_edges.observation_count + 1,
                confidence = GREATEST(network_edges.confidence, EXCLUDED.confidence),
                location = COALESCE(EXCLUDED.location, network_edges.location),
                details = EXCLUDED.details
        """),
        params,
    )


async def get_vessel_network(
    session: AsyncSession,
    mmsi: int,
    *,
    edge_type: Optional[str] = None,
    min_confidence: Optional[float] = None,
    since: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Return all edges connected to a vessel with optional filters."""
    clauses = ["(vessel_a_mmsi = :mmsi OR vessel_b_mmsi = :mmsi)"]
    params: dict[str, Any] = {"mmsi": mmsi}

    if edge_type:
        clauses.append("edge_type = :edge_type")
        params["edge_type"] = edge_type
    if min_confidence is not None:
        clauses.append("confidence >= :min_confidence")
        params["min_confidence"] = min_confidence
    if since:
        clauses.append("last_observed >= :since")
        params["since"] = since

    where = f"WHERE {' AND '.join(clauses)}"
    result = await session.execute(
        text(
            f"SELECT id, vessel_a_mmsi, vessel_b_mmsi, edge_type, confidence, "
            f"first_observed, last_observed, observation_count, "
            f"ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon, "
            f"details "
            f"FROM network_edges {where} "
            f"ORDER BY last_observed DESC"
        ),
        params,
    )
    return [dict(r) for r in result.mappings().all()]


async def get_connected_vessels(
    session: AsyncSession, mmsi: int
) -> set[int]:
    """Return set of direct neighbor MMSIs for a vessel."""
    result = await session.execute(
        text("""
            SELECT DISTINCT
                CASE
                    WHEN vessel_a_mmsi = :mmsi THEN vessel_b_mmsi
                    ELSE vessel_a_mmsi
                END AS neighbor_mmsi
            FROM network_edges
            WHERE vessel_a_mmsi = :mmsi OR vessel_b_mmsi = :mmsi
        """),
        {"mmsi": mmsi},
    )
    return {row[0] for row in result.all()}


async def get_network_cluster(
    session: AsyncSession, mmsi: int, max_depth: int = 5
) -> set[int]:
    """BFS traversal returning all MMSIs in the connected component.

    Starts from *mmsi* and expands outward up to *max_depth* hops.
    Returns the full set of MMSIs including the starting vessel.
    """
    visited: set[int] = {mmsi}
    frontier: set[int] = {mmsi}

    for _ in range(max_depth):
        if not frontier:
            break

        # Fetch all neighbors of the current frontier in one query
        placeholders = ", ".join(str(m) for m in frontier)
        result = await session.execute(
            text(f"""
                SELECT DISTINCT vessel_a_mmsi, vessel_b_mmsi
                FROM network_edges
                WHERE vessel_a_mmsi IN ({placeholders})
                   OR vessel_b_mmsi IN ({placeholders})
            """),
        )

        next_frontier: set[int] = set()
        for row in result.all():
            a, b = row[0], row[1]
            if a not in visited:
                next_frontier.add(a)
            if b not in visited:
                next_frontier.add(b)

        visited.update(next_frontier)
        frontier = next_frontier

    return visited
