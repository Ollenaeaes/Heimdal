"""Tests for port-awareness helpers (Story 2 of spec 17).

Verifies the ``is_near_port`` function and the 007_ports migration seed data.
All database interactions are mocked — no running services needed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Make the scoring service importable
_scoring_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scoring_dir))
# Make shared importable
sys.path.insert(0, str(_scoring_dir.parent.parent))

from rules.zone_helpers import is_near_port

# Path to the migration file for seed-data assertions
_MIGRATION_FILE = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "db"
    / "migrations"
    / "007_ports.sql"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session(row: tuple | None) -> AsyncMock:
    """Return an ``AsyncSession`` mock whose execute returns *row*."""
    result = MagicMock()
    result.first.return_value = row

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


# ---------------------------------------------------------------------------
# is_near_port behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_near_port_returns_name_when_within_range():
    """When the DB finds a port within range, the port name is returned."""
    session = _mock_session(("Rotterdam",))
    name = await is_near_port(session, lat=51.9, lon=4.0)
    assert name == "Rotterdam"

    # Verify the query was called with correct buffer (5 nm default)
    call_args = session.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert params["buffer"] == 5 * 1852


@pytest.mark.asyncio
async def test_near_port_returns_none_when_far():
    """When no port is within range, None is returned."""
    session = _mock_session(None)
    name = await is_near_port(session, lat=0.0, lon=0.0)
    assert name is None


@pytest.mark.asyncio
async def test_near_port_custom_radius():
    """A custom radius_nm is correctly converted to metres."""
    session = _mock_session(("Singapore",))
    name = await is_near_port(session, lat=1.26, lon=103.85, radius_nm=10.0)
    assert name == "Singapore"

    call_args = session.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert params["buffer"] == 10 * 1852


# ---------------------------------------------------------------------------
# Migration seed-data validation
# ---------------------------------------------------------------------------


def _read_migration() -> str:
    """Read the 007_ports.sql migration file."""
    return _MIGRATION_FILE.read_text()


def _extract_port_names(sql: str) -> list[str]:
    """Extract port names from INSERT VALUES in the migration SQL."""
    # Match the name field inside each VALUES tuple: ('PortName', ...
    return re.findall(r"\('([^']+)',\s*'[A-Z]{2}'", sql)


def test_migration_seeds_at_least_50_ports():
    sql = _read_migration()
    names = _extract_port_names(sql)
    assert len(names) >= 50, f"Expected >=50 ports, found {len(names)}: {names}"


def test_migration_includes_all_russian_terminals():
    sql = _read_migration()
    names = _extract_port_names(sql)
    russian_terminals = {
        "Novorossiysk",
        "Primorsk",
        "Ust-Luga",
        "Kozmino",
        "Murmansk",
        "Taman",
        "Vysotsk",
    }
    missing = russian_terminals - set(names)
    assert not missing, f"Missing Russian terminals: {missing}"


def test_migration_includes_indian_refinery_ports():
    sql = _read_migration()
    names = _extract_port_names(sql)
    indian_ports = {"Sikka (Jamnagar)", "Paradip", "Vadinar", "Mumbai (JNPT)", "Chennai"}
    missing = indian_ports - set(names)
    assert not missing, f"Missing Indian ports: {missing}"


def test_migration_includes_chinese_refinery_ports():
    sql = _read_migration()
    names = _extract_port_names(sql)
    chinese_ports = {"Qingdao", "Rizhao", "Dongying", "Zhoushan", "Ningbo", "Dalian"}
    missing = chinese_ports - set(names)
    assert not missing, f"Missing Chinese ports: {missing}"


def test_migration_includes_turkish_refinery_ports():
    sql = _read_migration()
    names = _extract_port_names(sql)
    turkish_ports = {"Iskenderun", "Mersin", "Aliaga", "Dortyol", "Ceyhan"}
    missing = turkish_ports - set(names)
    assert not missing, f"Missing Turkish ports: {missing}"
