"""Network risk score calculation for sanctions evasion network mapping.

Computes a network-based risk score for vessels by traversing their
connected component and checking for proximity to sanctioned entities.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.network_repository import get_connected_vessels, get_network_cluster

logger = logging.getLogger("scoring.network_scorer")

# Score points by hop distance from sanctioned vessel
_HOP_SCORES = {
    1: 30,
    2: 15,
}
_DEFAULT_HOP_SCORE = 5

# Pattern bonus: cluster with >= 3 vessels having Russian port visits + STS anomalies
_PATTERN_THRESHOLD = 3
_PATTERN_BONUS = 20


async def _get_sanctioned_mmsis(session: AsyncSession, mmsis: set[int]) -> set[int]:
    """Return subset of MMSIs that have a non-empty sanctions_status."""
    if not mmsis:
        return set()

    placeholders = ", ".join(str(m) for m in mmsis)
    result = await session.execute(
        text(f"""
            SELECT mmsi FROM vessel_profiles
            WHERE mmsi IN ({placeholders})
              AND sanctions_status IS NOT NULL
              AND sanctions_status != '{{}}'::jsonb
              AND sanctions_status != 'null'::jsonb
        """),
    )
    return {row[0] for row in result.all()}


async def _get_pattern_vessels(session: AsyncSession, mmsis: set[int]) -> set[int]:
    """Return MMSIs that have both Russian port visits and STS anomalies.

    Checks for:
    - gfw_port_visit events at Russian terminals
    - Active STS-related anomaly events
    """
    if not mmsis:
        return set()

    placeholders = ", ".join(str(m) for m in mmsis)

    # Vessels with Russian port visits (via GFW events)
    result = await session.execute(
        text(f"""
            SELECT DISTINCT mmsi FROM gfw_events
            WHERE mmsi IN ({placeholders})
              AND event_type = 'port_visit'
              AND (
                  LOWER(port_name) LIKE '%ust-luga%'
                  OR LOWER(port_name) LIKE '%primorsk%'
                  OR LOWER(port_name) LIKE '%novorossiysk%'
                  OR LOWER(port_name) LIKE '%kozmino%'
                  OR LOWER(port_name) LIKE '%murmansk%'
                  OR LOWER(port_name) LIKE '%taman%'
                  OR LOWER(port_name) LIKE '%vysotsk%'
                  OR LOWER(port_name) LIKE '%de kastri%'
                  OR LOWER(port_name) LIKE '%varandey%'
              )
        """),
    )
    russian_port_vessels = {row[0] for row in result.all()}

    # Vessels with STS-related anomalies
    result = await session.execute(
        text(f"""
            SELECT DISTINCT mmsi FROM anomaly_events
            WHERE mmsi IN ({placeholders})
              AND resolved = false
              AND (rule_id LIKE '%sts%' OR rule_id LIKE '%loitering%')
        """),
    )
    sts_anomaly_vessels = {row[0] for row in result.all()}

    return russian_port_vessels & sts_anomaly_vessels


async def calculate_network_score(
    session: AsyncSession, mmsi: int
) -> int:
    """Calculate network risk score for a vessel using BFS hop decay.

    Scoring:
    - 1 hop from sanctioned vessel: 30 points per sanctioned vessel
    - 2 hops: 15 points per sanctioned vessel
    - 3+ hops: 5 points per sanctioned vessel
    - Pattern bonus: cluster with >=3 vessels having Russian port visits
      + STS anomalies -> 20 points per such vessel

    Stores result in vessel_profiles.network_score.
    Returns the calculated score.
    """
    # Get full cluster
    cluster = await get_network_cluster(session, mmsi)

    if len(cluster) <= 1:
        # Isolated vessel — no network score
        await _store_network_score(session, mmsi, 0)
        return 0

    # BFS from this vessel to find hop distances
    hop_distances: dict[int, int] = {mmsi: 0}
    frontier: set[int] = {mmsi}
    depth = 0

    while frontier and depth < 10:
        depth += 1
        next_frontier: set[int] = set()
        for vessel in frontier:
            neighbors = await get_connected_vessels(session, vessel)
            for neighbor in neighbors:
                if neighbor not in hop_distances:
                    hop_distances[neighbor] = depth
                    next_frontier.add(neighbor)
        frontier = next_frontier

    # Find sanctioned vessels in the cluster
    other_vessels = cluster - {mmsi}
    sanctioned = await _get_sanctioned_mmsis(session, other_vessels)

    # Calculate hop-decay score
    score = 0
    for s_mmsi in sanctioned:
        hops = hop_distances.get(s_mmsi, 999)
        if hops <= 0:
            continue
        score += _HOP_SCORES.get(hops, _DEFAULT_HOP_SCORE)

    # Pattern bonus
    pattern_vessels = await _get_pattern_vessels(session, cluster)
    if len(pattern_vessels) >= _PATTERN_THRESHOLD:
        score += len(pattern_vessels) * _PATTERN_BONUS

    await _store_network_score(session, mmsi, score)
    return score


async def _store_network_score(
    session: AsyncSession, mmsi: int, score: int
) -> None:
    """Store the network_score in vessel_profiles."""
    await session.execute(
        text(
            "UPDATE vessel_profiles "
            "SET network_score = :score, updated_at = NOW() "
            "WHERE mmsi = :mmsi"
        ),
        {"mmsi": mmsi, "score": score},
    )


async def recalculate_cluster_scores(
    session: AsyncSession, mmsi: int
) -> dict[int, int]:
    """Recalculate network scores for the entire cluster containing a vessel.

    Returns a dict mapping each MMSI in the cluster to its new score.
    """
    cluster = await get_network_cluster(session, mmsi)

    scores: dict[int, int] = {}
    for vessel_mmsi in cluster:
        score = await calculate_network_score(session, vessel_mmsi)
        scores[vessel_mmsi] = score

    logger.info(
        "cluster_scores_recalculated",
        extra={
            "seed_mmsi": mmsi,
            "cluster_size": len(cluster),
            "scores": scores,
        },
    )
    return scores
