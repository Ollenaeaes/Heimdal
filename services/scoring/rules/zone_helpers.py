"""Shared spatial helpers for zone proximity checks.

These helpers query the ``zones`` table using PostGIS ``ST_DWithin`` to
determine whether a given lat/lon falls within (or near) a known STS zone
or Russian terminal.  They are used by multiple GFW-sourced scoring rules.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 10 nautical miles in metres (1 nm = 1852 m)
_10NM_METRES = 18_520

# Known Russian terminal port names (matching zone seed data).
RUSSIAN_TERMINAL_NAMES: frozenset[str] = frozenset({
    "Ust-Luga",
    "Primorsk",
    "Novorossiysk",
    "Kozmino",
    "Murmansk",
    "Taman",
    "Vysotsk",
    # Aliases that may appear in GFW port_name field:
    "De Kastri",
    "Varandey",
})


async def is_in_sts_zone(
    session: AsyncSession,
    lat: float,
    lon: float,
    buffer_m: int = _10NM_METRES,
) -> Optional[str]:
    """Return the STS zone name if *lat*/*lon* is within *buffer_m* of one.

    Returns ``None`` if the point is not near any STS zone.
    """
    result = await session.execute(
        text("""
            SELECT zone_name FROM zones
            WHERE zone_type = 'sts_zone'
              AND ST_DWithin(
                    geometry,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    :buffer
              )
            LIMIT 1
        """),
        {"lat": lat, "lon": lon, "buffer": buffer_m},
    )
    row = result.first()
    return row[0] if row else None


async def is_near_russian_terminal(
    session: AsyncSession,
    lat: float,
    lon: float,
    buffer_m: int = _10NM_METRES,
) -> Optional[str]:
    """Return the terminal zone name if *lat*/*lon* is near a Russian terminal.

    Returns ``None`` if the point is not near any terminal.
    """
    result = await session.execute(
        text("""
            SELECT zone_name FROM zones
            WHERE zone_type = 'terminal'
              AND ST_DWithin(
                    geometry,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    :buffer
              )
            LIMIT 1
        """),
        {"lat": lat, "lon": lon, "buffer": buffer_m},
    )
    row = result.first()
    return row[0] if row else None


def is_russian_terminal_port(port_name: Optional[str]) -> bool:
    """Check if a port name matches a known Russian terminal.

    Performs a case-insensitive substring match against the known set.
    """
    if not port_name:
        return False
    port_lower = port_name.lower()
    return any(t.lower() in port_lower for t in RUSSIAN_TERMINAL_NAMES)
