"""Shared spatial helpers for infrastructure corridor checks.

Provides proximity queries against the ``infrastructure_routes`` table to
determine whether a vessel position falls within a cable or pipeline
corridor.  Used by infrastructure-protection scoring rules.

Follows the pattern established by ``zone_helpers.py``.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def is_in_infrastructure_corridor(
    session: AsyncSession,
    lat: float,
    lon: float,
) -> list[dict[str, Any]]:
    """Return matching infrastructure route records where the position is
    within ``buffer_nm`` nautical miles of the route geometry.

    Each dict has keys: id, name, route_type, operator, buffer_nm, metadata.
    Returns an empty list if no routes match.
    """
    result = await session.execute(
        text("""
            SELECT id, name, route_type, operator, buffer_nm, metadata
            FROM infrastructure_routes
            WHERE ST_DWithin(
                    geometry,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    buffer_nm * 1852.0
            )
        """),
        {"lat": lat, "lon": lon},
    )
    rows = result.fetchall()
    return [
        {
            "id": row[0],
            "name": row[1],
            "route_type": row[2],
            "operator": row[3],
            "buffer_nm": row[4],
            "metadata": row[5],
        }
        for row in rows
    ]


async def compute_cable_bearing(
    session: AsyncSession,
    lat: float,
    lon: float,
    route_id: int,
) -> Optional[float]:
    """Return the bearing (0-360) of the nearest segment on the given route.

    Uses PostGIS ``ST_ClosestPoint`` to find the nearest point, then
    computes the bearing of the segment containing that point.
    Returns ``None`` if the route is not found or computation fails.
    """
    result = await session.execute(
        text("""
            WITH nearest AS (
                SELECT
                    geometry,
                    ST_LineLocatePoint(
                        geometry::geometry,
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
                    ) AS frac
                FROM infrastructure_routes
                WHERE id = :route_id
            )
            SELECT
                ST_X(ST_LineInterpolatePoint(geometry::geometry, GREATEST(frac - 0.001, 0))) AS x1,
                ST_Y(ST_LineInterpolatePoint(geometry::geometry, GREATEST(frac - 0.001, 0))) AS y1,
                ST_X(ST_LineInterpolatePoint(geometry::geometry, LEAST(frac + 0.001, 1))) AS x2,
                ST_Y(ST_LineInterpolatePoint(geometry::geometry, LEAST(frac + 0.001, 1))) AS y2
            FROM nearest
        """),
        {"lat": lat, "lon": lon, "route_id": route_id},
    )
    row = result.first()
    if row is None:
        return None

    lon1, lat1, lon2, lat2 = row[0], row[1], row[2], row[3]
    if lon1 is None or lat1 is None or lon2 is None or lat2 is None:
        return None

    # Compute bearing from (lat1, lon1) to (lat2, lon2)
    d_lon = math.radians(lon2 - lon1)
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)

    x = math.sin(d_lon) * math.cos(lat2_r)
    y = (
        math.cos(lat1_r) * math.sin(lat2_r)
        - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(d_lon)
    )
    bearing = math.degrees(math.atan2(x, y))
    return bearing % 360


def angle_difference(cog: float, bearing: float) -> float:
    """Return the minimum angular difference (0-180) between two headings.

    Correctly handles the 360-degree wraparound.

    Parameters
    ----------
    cog : float
        Course over ground (0-360 degrees).
    bearing : float
        Cable/pipeline bearing (0-360 degrees).
    """
    diff = abs(cog - bearing) % 360
    if diff > 180:
        diff = 360 - diff
    return diff


async def is_in_port_approach(
    session: AsyncSession,
    lat: float,
    lon: float,
) -> bool:
    """Return True if the position is within 10 nm of a known port.

    Reuses the ``ports`` table (seeded by migration 007) with a 10 nm
    radius, matching the port approach zone concept.
    """
    from .zone_helpers import is_near_port

    port_name = await is_near_port(session, lat, lon, radius_nm=10.0)
    return port_name is not None
