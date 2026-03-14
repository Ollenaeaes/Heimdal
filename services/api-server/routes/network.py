"""Network REST endpoints for the Heimdal API server.

Provides:
- GET /api/vessels/{mmsi}/network  — vessel's direct edges with depth/type filter
- GET /api/network/clusters        — summary of largest connected components
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from shared.db.connection import get_session

logger = logging.getLogger("api-server.network")

router = APIRouter(prefix="/api", tags=["network"])


@router.get("/vessels/{mmsi}/network")
async def get_vessel_network(
    mmsi: int,
    depth: int = Query(1, ge=1, le=3, description="How many hops to traverse (max 3)"),
    edge_type: Optional[str] = Query(None, description="Filter by edge type"),
):
    """Return a vessel's network edges with optional depth traversal.

    Returns edges and basic profile data for connected vessels.
    """
    session_factory = get_session()
    async with session_factory() as session:
        # Verify vessel exists
        result = await session.execute(
            text("SELECT mmsi, ship_name, flag_country, risk_tier, ship_type, network_score "
                 "FROM vessel_profiles WHERE mmsi = :mmsi"),
            {"mmsi": mmsi},
        )
        vessel = result.mappings().first()
        if not vessel:
            raise HTTPException(status_code=404, detail="Vessel not found")

        # BFS to collect edges up to requested depth
        visited: set[int] = {mmsi}
        frontier: set[int] = {mmsi}
        all_edges: list[dict] = []

        for _ in range(depth):
            if not frontier:
                break

            # Build edge query for current frontier
            placeholders = ", ".join(str(m) for m in frontier)
            edge_clauses = [
                f"(vessel_a_mmsi IN ({placeholders}) OR vessel_b_mmsi IN ({placeholders}))"
            ]
            params: dict = {}

            if edge_type:
                edge_clauses.append("edge_type = :edge_type")
                params["edge_type"] = edge_type

            where = " AND ".join(edge_clauses)
            result = await session.execute(
                text(
                    f"SELECT id, vessel_a_mmsi, vessel_b_mmsi, edge_type, "
                    f"confidence, first_observed, last_observed, observation_count, "
                    f"ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon, "
                    f"details "
                    f"FROM network_edges WHERE {where} "
                    f"ORDER BY last_observed DESC"
                ),
                params,
            )

            next_frontier: set[int] = set()
            for row in result.mappings().all():
                edge = dict(row)
                # Avoid duplicate edges
                if not any(e["id"] == edge["id"] for e in all_edges):
                    all_edges.append(edge)
                a, b = edge["vessel_a_mmsi"], edge["vessel_b_mmsi"]
                if a not in visited:
                    next_frontier.add(a)
                if b not in visited:
                    next_frontier.add(b)

            visited.update(next_frontier)
            frontier = next_frontier

        # Fetch profile data for all connected vessels
        connected_mmsis = visited - {mmsi}
        vessels_data: dict[int, dict] = {
            mmsi: dict(vessel),
        }

        if connected_mmsis:
            placeholders = ", ".join(str(m) for m in connected_mmsis)
            result = await session.execute(
                text(
                    f"SELECT mmsi, ship_name, flag_country, risk_tier, ship_type, network_score "
                    f"FROM vessel_profiles "
                    f"WHERE mmsi IN ({placeholders})"
                ),
            )
            for row in result.mappings().all():
                vessels_data[row["mmsi"]] = dict(row)

    return {
        "mmsi": mmsi,
        "depth": depth,
        "edges": all_edges,
        "vessels": vessels_data,
    }


@router.get("/network/clusters")
async def get_network_clusters(
    min_size: int = Query(2, ge=2, description="Minimum cluster size"),
    limit: int = Query(20, ge=1, le=100),
):
    """Return summary of largest connected components.

    Uses a CTE-based approach to find connected components and returns
    cluster size, max risk tier, and count of sanctioned vessels.
    """
    session_factory = get_session()
    async with session_factory() as session:
        # Get all edges and build clusters in Python (more reliable than
        # trying to do connected components in pure SQL)
        result = await session.execute(
            text("SELECT vessel_a_mmsi, vessel_b_mmsi FROM network_edges"),
        )
        edges = result.all()

        if not edges:
            return {"clusters": [], "total": 0}

        # Build adjacency list
        adjacency: dict[int, set[int]] = {}
        for a, b in edges:
            adjacency.setdefault(a, set()).add(b)
            adjacency.setdefault(b, set()).add(a)

        # Find connected components via BFS
        all_mmsis = set(adjacency.keys())
        visited: set[int] = set()
        clusters: list[set[int]] = []

        for start in all_mmsis:
            if start in visited:
                continue
            component: set[int] = set()
            queue = [start]
            while queue:
                node = queue.pop()
                if node in component:
                    continue
                component.add(node)
                for neighbor in adjacency.get(node, set()):
                    if neighbor not in component:
                        queue.append(neighbor)
            visited.update(component)
            if len(component) >= min_size:
                clusters.append(component)

        # Sort by size descending, take top N
        clusters.sort(key=len, reverse=True)
        clusters = clusters[:limit]

        if not clusters:
            return {"clusters": [], "total": 0}

        # Fetch profile data for all vessels in retained clusters
        all_cluster_mmsis = set()
        for c in clusters:
            all_cluster_mmsis.update(c)

        placeholders = ", ".join(str(m) for m in all_cluster_mmsis)
        result = await session.execute(
            text(
                f"SELECT mmsi, risk_tier, sanctions_status, ship_name, flag_country, ship_type "
                f"FROM vessel_profiles WHERE mmsi IN ({placeholders})"
            ),
        )
        profiles: dict[int, dict] = {}
        for row in result.mappings().all():
            profiles[row["mmsi"]] = dict(row)

        # Build cluster summaries
        cluster_summaries = []
        for component in clusters:
            risk_tiers = []
            sanctioned_count = 0
            members = []

            for m in component:
                profile = profiles.get(m, {})
                tier = profile.get("risk_tier", "green")
                risk_tiers.append(tier)

                sanctions = profile.get("sanctions_status")
                if sanctions and sanctions != {} and sanctions != "null":
                    sanctioned_count += 1

                members.append({
                    "mmsi": m,
                    "ship_name": profile.get("ship_name"),
                    "flag_country": profile.get("flag_country"),
                    "risk_tier": tier,
                    "ship_type": profile.get("ship_type"),
                })

            # Determine max risk tier
            tier_order = {"red": 3, "yellow": 2, "green": 1}
            max_tier = max(risk_tiers, key=lambda t: tier_order.get(t, 0)) if risk_tiers else "green"

            cluster_summaries.append({
                "cluster_size": len(component),
                "max_risk_tier": max_tier,
                "sanctioned_count": sanctioned_count,
                "members": members,
            })

    return {
        "clusters": cluster_summaries,
        "total": len(cluster_summaries),
    }
