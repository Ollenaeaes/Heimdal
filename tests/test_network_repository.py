"""Tests for shared/db/network_repository.py.

Verifies:
- MMSI normalization (min/max ordering)
- upsert_network_edge SQL correctness (with and without location)
- get_vessel_network query construction with filters
- get_connected_vessels returns correct neighbor set
- get_network_cluster BFS traversal with cycles
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from shared.db.network_repository import (
    _normalize_mmsi_pair,
    get_connected_vessels,
    get_network_cluster,
    get_vessel_network,
    upsert_network_edge,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_session(
    rows: list[dict[str, Any]] | None = None,
    scalar: Any = None,
    raw_rows: list[tuple] | None = None,
):
    """Create an AsyncMock session that returns configurable results."""
    session = AsyncMock()
    result_mock = MagicMock()

    if rows is not None:
        mappings_mock = MagicMock()
        mapping_rows = []
        for r in rows:
            row_mock = MagicMock()
            row_mock.__iter__ = lambda s, _r=r: iter(_r.items())
            row_mock.keys = lambda _r=r: _r.keys()
            row_mock.__getitem__ = lambda s, k, _r=r: _r[k]
            row_mock.items = lambda _r=r: _r.items()
            row_mock.get = lambda k, d=None, _r=r: _r.get(k, d)
            mapping_rows.append(row_mock)
        mappings_mock.all.return_value = mapping_rows
        mappings_mock.first.return_value = mapping_rows[0] if mapping_rows else None
        result_mock.mappings.return_value = mappings_mock

    if raw_rows is not None:
        result_mock.all.return_value = raw_rows
        result_mock.first.return_value = raw_rows[0] if raw_rows else None

    if scalar is not None:
        result_mock.scalar.return_value = scalar

    session.execute.return_value = result_mock
    return session


# ---------------------------------------------------------------------------
# MMSI Normalization
# ---------------------------------------------------------------------------


class TestNormalizeMmsiPair:
    def test_already_ordered(self):
        assert _normalize_mmsi_pair(100, 200) == (100, 200)

    def test_reversed_order(self):
        assert _normalize_mmsi_pair(200, 100) == (100, 200)

    def test_equal_mmsi(self):
        assert _normalize_mmsi_pair(100, 100) == (100, 100)

    def test_large_mmsi_values(self):
        assert _normalize_mmsi_pair(999999999, 111111111) == (111111111, 999999999)


# ---------------------------------------------------------------------------
# Upsert Network Edge
# ---------------------------------------------------------------------------


class TestUpsertNetworkEdge:
    @pytest.mark.asyncio
    async def test_upsert_with_location(self):
        session = _make_mock_session()
        await upsert_network_edge(
            session,
            mmsi_a=200,
            mmsi_b=100,
            edge_type="encounter",
            confidence=1.0,
            location={"lat": 55.0, "lon": 25.0},
            details={"event": "test"},
        )

        session.execute.assert_called_once()
        call_args = session.execute.call_args
        params = call_args[0][1]

        # MMSI should be normalized (min first)
        assert params["vessel_a"] == 100
        assert params["vessel_b"] == 200
        assert params["edge_type"] == "encounter"
        assert params["confidence"] == 1.0
        assert params["lat"] == 55.0
        assert params["lon"] == 25.0
        assert params["details"] == {"event": "test"}

    @pytest.mark.asyncio
    async def test_upsert_without_location(self):
        session = _make_mock_session()
        await upsert_network_edge(
            session,
            mmsi_a=100,
            mmsi_b=200,
            edge_type="ownership",
            confidence=1.0,
            location=None,
        )

        session.execute.assert_called_once()
        call_args = session.execute.call_args
        sql_text = str(call_args[0][0].text)
        params = call_args[0][1]

        assert "NULL" in sql_text
        assert "lat" not in params
        assert "lon" not in params

    @pytest.mark.asyncio
    async def test_upsert_normalizes_mmsi_order(self):
        session = _make_mock_session()
        await upsert_network_edge(session, mmsi_a=500, mmsi_b=100, edge_type="encounter")

        params = session.execute.call_args[0][1]
        assert params["vessel_a"] == 100
        assert params["vessel_b"] == 500

    @pytest.mark.asyncio
    async def test_upsert_default_details(self):
        session = _make_mock_session()
        await upsert_network_edge(session, mmsi_a=100, mmsi_b=200, edge_type="encounter")

        params = session.execute.call_args[0][1]
        assert params["details"] == {}

    @pytest.mark.asyncio
    async def test_upsert_sql_has_on_conflict(self):
        session = _make_mock_session()
        await upsert_network_edge(session, mmsi_a=100, mmsi_b=200, edge_type="encounter")

        sql_text = str(session.execute.call_args[0][0].text)
        assert "ON CONFLICT" in sql_text
        assert "observation_count" in sql_text
        assert "GREATEST" in sql_text


# ---------------------------------------------------------------------------
# Get Vessel Network
# ---------------------------------------------------------------------------


class TestGetVesselNetwork:
    @pytest.mark.asyncio
    async def test_basic_query(self):
        session = _make_mock_session(rows=[])
        result = await get_vessel_network(session, 100)
        assert result == []
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_edge_type_filter(self):
        session = _make_mock_session(rows=[])
        await get_vessel_network(session, 100, edge_type="encounter")

        sql_text = str(session.execute.call_args[0][0].text)
        assert "edge_type = :edge_type" in sql_text
        params = session.execute.call_args[0][1]
        assert params["edge_type"] == "encounter"

    @pytest.mark.asyncio
    async def test_with_min_confidence(self):
        session = _make_mock_session(rows=[])
        await get_vessel_network(session, 100, min_confidence=0.5)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "confidence >= :min_confidence" in sql_text
        params = session.execute.call_args[0][1]
        assert params["min_confidence"] == 0.5

    @pytest.mark.asyncio
    async def test_with_since_filter(self):
        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        session = _make_mock_session(rows=[])
        await get_vessel_network(session, 100, since=since)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "last_observed >= :since" in sql_text

    @pytest.mark.asyncio
    async def test_returns_dict_list(self):
        rows = [
            {
                "id": 1,
                "vessel_a_mmsi": 100,
                "vessel_b_mmsi": 200,
                "edge_type": "encounter",
                "confidence": 1.0,
                "first_observed": datetime.now(),
                "last_observed": datetime.now(),
                "observation_count": 1,
                "lat": 55.0,
                "lon": 25.0,
                "details": {},
            }
        ]
        session = _make_mock_session(rows=rows)
        result = await get_vessel_network(session, 100)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Get Connected Vessels
# ---------------------------------------------------------------------------


class TestGetConnectedVessels:
    @pytest.mark.asyncio
    async def test_returns_neighbor_set(self):
        session = _make_mock_session(raw_rows=[(200,), (300,)])
        result = await get_connected_vessels(session, 100)
        assert result == {200, 300}

    @pytest.mark.asyncio
    async def test_empty_network(self):
        session = _make_mock_session(raw_rows=[])
        result = await get_connected_vessels(session, 100)
        assert result == set()


# ---------------------------------------------------------------------------
# Get Network Cluster (BFS)
# ---------------------------------------------------------------------------


class TestGetNetworkCluster:
    @pytest.mark.asyncio
    async def test_isolated_vessel(self):
        """Vessel with no edges returns only itself."""
        session = _make_mock_session(raw_rows=[])
        result = await get_network_cluster(session, 100)
        assert result == {100}

    @pytest.mark.asyncio
    async def test_linear_chain(self):
        """A -> B -> C should return {A, B, C}."""
        call_count = 0

        async def mock_execute(sql_text, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result_mock = MagicMock()
            if call_count == 1:
                # Frontier: {100} -> neighbors: edges (100,200)
                result_mock.all.return_value = [(100, 200)]
            elif call_count == 2:
                # Frontier: {200} -> neighbors: edges (200,300)
                result_mock.all.return_value = [(200, 300)]
            else:
                # Frontier: {300} -> no new edges
                result_mock.all.return_value = []
            return result_mock

        session = AsyncMock()
        session.execute = mock_execute
        result = await get_network_cluster(session, 100, max_depth=5)
        assert result == {100, 200, 300}

    @pytest.mark.asyncio
    async def test_cycle_handling(self):
        """BFS should handle cycles without infinite loop."""
        call_count = 0

        async def mock_execute(sql_text, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result_mock = MagicMock()
            if call_count == 1:
                # 100 -> 200, 300
                result_mock.all.return_value = [(100, 200), (100, 300)]
            elif call_count == 2:
                # 200 -> 100, 300 (cycle back)
                result_mock.all.return_value = [(200, 100), (200, 300), (300, 100)]
            else:
                result_mock.all.return_value = []
            return result_mock

        session = AsyncMock()
        session.execute = mock_execute
        result = await get_network_cluster(session, 100, max_depth=5)
        assert result == {100, 200, 300}

    @pytest.mark.asyncio
    async def test_max_depth_limits_traversal(self):
        """BFS should stop at max_depth."""
        call_count = 0

        async def mock_execute(sql_text, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result_mock = MagicMock()
            if call_count == 1:
                result_mock.all.return_value = [(100, 200)]
            elif call_count == 2:
                result_mock.all.return_value = [(200, 300)]
            else:
                result_mock.all.return_value = [(300, 400)]
            return result_mock

        session = AsyncMock()
        session.execute = mock_execute
        result = await get_network_cluster(session, 100, max_depth=2)
        assert 100 in result
        assert 200 in result
        assert 300 in result
        # 400 should NOT be included since max_depth=2
