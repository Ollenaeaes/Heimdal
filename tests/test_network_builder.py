"""Tests for services/scoring/network_builder.py.

Verifies:
- Encounter edge creation with valid profiles
- Encounter edge skip when profile is missing
- Proximity edge creation in STS zones
- Proximity edge skip for non-STS zones
- Ownership edge creation by registered_owner
- Ownership edge creation by commercial_manager
- Ownership edge skip when no ownership data
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.scoring.network_builder import (
    create_encounter_edge,
    create_ownership_edges,
    create_proximity_edges,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile_check_session(
    profiles_exist: set[int] | None = None,
    extra_queries: list | None = None,
):
    """Create a mock session that checks vessel_profiles existence.

    profiles_exist: set of MMSIs that should exist
    extra_queries: list of (result_type, data) for subsequent calls
    """
    profiles_exist = profiles_exist or set()
    extra_queries = extra_queries or []
    call_index = [0]

    async def mock_execute(sql_text, params=None, *args, **kwargs):
        nonlocal call_index
        sql_str = str(sql_text.text) if hasattr(sql_text, 'text') else str(sql_text)
        result_mock = MagicMock()

        if "SELECT 1 FROM vessel_profiles" in sql_str:
            mmsi_val = params.get("mmsi") if params else None
            if mmsi_val in profiles_exist:
                result_mock.first.return_value = (1,)
            else:
                result_mock.first.return_value = None
            return result_mock

        if call_index[0] < len(extra_queries):
            qtype, data = extra_queries[call_index[0]]
            call_index[0] += 1
            if qtype == "rows":
                result_mock.all.return_value = data
            elif qtype == "mappings":
                mappings_mock = MagicMock()
                mapping_rows = []
                for r in data:
                    row_mock = MagicMock()
                    row_mock.__getitem__ = lambda s, k, _r=r: _r[k]
                    row_mock.get = lambda k, d=None, _r=r: _r.get(k, d)
                    mapping_rows.append(row_mock)
                mappings_mock.all.return_value = mapping_rows
                mappings_mock.first.return_value = mapping_rows[0] if mapping_rows else None
                result_mock.mappings.return_value = mappings_mock
            elif qtype == "first":
                result_mock.first.return_value = data
        else:
            result_mock.all.return_value = []
            result_mock.first.return_value = None
            mappings_mock = MagicMock()
            mappings_mock.all.return_value = []
            mappings_mock.first.return_value = None
            result_mock.mappings.return_value = mappings_mock

        return result_mock

    session = AsyncMock()
    session.execute = mock_execute
    return session


# ---------------------------------------------------------------------------
# Encounter Edge Creation
# ---------------------------------------------------------------------------


class TestCreateEncounterEdge:
    @pytest.mark.asyncio
    @patch("services.scoring.network_builder.upsert_network_edge")
    async def test_creates_edge_when_profiles_exist(self, mock_upsert):
        session = _make_profile_check_session(profiles_exist={100, 200})
        await create_encounter_edge(
            session,
            mmsi_a=100,
            mmsi_b=200,
            location_lat=55.0,
            location_lon=25.0,
            observed_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
            details={"event_id": "abc"},
        )

        mock_upsert.assert_called_once_with(
            session,
            mmsi_a=100,
            mmsi_b=200,
            edge_type="encounter",
            confidence=1.0,
            location={"lat": 55.0, "lon": 25.0},
            details={"event_id": "abc"},
        )

    @pytest.mark.asyncio
    @patch("services.scoring.network_builder.upsert_network_edge")
    async def test_skips_when_mmsi_a_missing(self, mock_upsert):
        session = _make_profile_check_session(profiles_exist={200})
        await create_encounter_edge(
            session,
            mmsi_a=100,
            mmsi_b=200,
            location_lat=55.0,
            location_lon=25.0,
            observed_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    @patch("services.scoring.network_builder.upsert_network_edge")
    async def test_skips_when_mmsi_b_missing(self, mock_upsert):
        session = _make_profile_check_session(profiles_exist={100})
        await create_encounter_edge(
            session,
            mmsi_a=100,
            mmsi_b=200,
            location_lat=55.0,
            location_lon=25.0,
            observed_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    @patch("services.scoring.network_builder.upsert_network_edge")
    async def test_default_details_includes_observed_at(self, mock_upsert):
        session = _make_profile_check_session(profiles_exist={100, 200})
        observed = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        await create_encounter_edge(
            session, 100, 200, 55.0, 25.0, observed_at=observed
        )

        call_kwargs = mock_upsert.call_args[1]
        assert "observed_at" in call_kwargs["details"]


# ---------------------------------------------------------------------------
# Proximity Edge Creation
# ---------------------------------------------------------------------------


class TestCreateProximityEdges:
    @pytest.mark.asyncio
    @patch("services.scoring.network_builder.upsert_network_edge")
    @patch("services.scoring.rules.zone_helpers.is_in_sts_zone")
    async def test_skips_non_sts_zone(self, mock_zone, mock_upsert):
        mock_zone.return_value = None  # Not in STS zone
        session = AsyncMock()
        result = await create_proximity_edges(
            session, 100, 55.0, 25.0, datetime.now(timezone.utc)
        )
        assert result == 0
        mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    @patch("services.scoring.network_builder.upsert_network_edge")
    @patch("services.scoring.rules.zone_helpers.is_in_sts_zone")
    async def test_creates_edges_in_sts_zone(self, mock_zone, mock_upsert):
        # First call: check if our location is in STS zone -> yes
        # Second call (per nearby vessel): check if their location is in same zone -> yes
        mock_zone.side_effect = ["Kalamata STS", "Kalamata STS"]

        session = _make_profile_check_session(
            profiles_exist={100, 200},
            extra_queries=[
                # GFW loitering events query: vessel 200 is nearby
                ("rows", [(200,)]),
                # Position query for vessel 200
                ("first", (55.1, 25.1)),
            ],
        )

        result = await create_proximity_edges(
            session, 100, 55.0, 25.0, datetime(2024, 6, 1, tzinfo=timezone.utc)
        )
        assert result == 1
        mock_upsert.assert_called_once()
        call_kwargs = mock_upsert.call_args[1]
        assert call_kwargs["edge_type"] == "proximity"
        assert call_kwargs["confidence"] == 0.7

    @pytest.mark.asyncio
    @patch("services.scoring.network_builder.upsert_network_edge")
    @patch("services.scoring.rules.zone_helpers.is_in_sts_zone")
    async def test_skips_missing_vessel_profile(self, mock_zone, mock_upsert):
        mock_zone.return_value = "Kalamata STS"
        session = _make_profile_check_session(profiles_exist=set())  # vessel 100 not in profiles

        result = await create_proximity_edges(
            session, 100, 55.0, 25.0, datetime.now(timezone.utc)
        )
        assert result == 0
        mock_upsert.assert_not_called()


# ---------------------------------------------------------------------------
# Ownership Edge Creation
# ---------------------------------------------------------------------------


class TestCreateOwnershipEdges:
    @pytest.mark.asyncio
    @patch("services.scoring.network_builder.upsert_network_edge")
    async def test_creates_edges_by_registered_owner(self, mock_upsert):
        session = AsyncMock()
        call_count = [0]

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            nonlocal call_count
            sql_str = str(sql_text.text) if hasattr(sql_text, 'text') else str(sql_text)
            result_mock = MagicMock()

            if "registered_owner, ownership_data" in sql_str:
                # Return the vessel's ownership data
                row_mock = MagicMock()
                row_mock.get = lambda k, d=None: {
                    "registered_owner": "Acme Shipping Co",
                    "ownership_data": {},
                }.get(k, d)
                mappings_mock = MagicMock()
                mappings_mock.first.return_value = row_mock
                result_mock.mappings.return_value = mappings_mock
            elif "LOWER(registered_owner)" in sql_str:
                result_mock.all.return_value = [(200,), (300,)]
            else:
                result_mock.all.return_value = []
            return result_mock

        session.execute = mock_execute
        result = await create_ownership_edges(session, 100)
        assert result == 2
        assert mock_upsert.call_count == 2

        # Verify edge details
        for c in mock_upsert.call_args_list:
            kwargs = c[1]
            assert kwargs["edge_type"] == "ownership"
            assert kwargs["confidence"] == 1.0
            assert kwargs["location"] is None

    @pytest.mark.asyncio
    @patch("services.scoring.network_builder.upsert_network_edge")
    async def test_creates_edges_by_commercial_manager(self, mock_upsert):
        session = AsyncMock()

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            sql_str = str(sql_text.text) if hasattr(sql_text, 'text') else str(sql_text)
            result_mock = MagicMock()

            if "registered_owner, ownership_data" in sql_str:
                row_mock = MagicMock()
                row_mock.get = lambda k, d=None: {
                    "registered_owner": None,
                    "ownership_data": {"commercial_manager": "Global Ship Mgmt"},
                }.get(k, d)
                mappings_mock = MagicMock()
                mappings_mock.first.return_value = row_mock
                result_mock.mappings.return_value = mappings_mock
            elif "commercial_manager" in sql_str:
                result_mock.all.return_value = [(400,)]
            else:
                result_mock.all.return_value = []
            return result_mock

        session.execute = mock_execute
        result = await create_ownership_edges(session, 100)
        assert result == 1

    @pytest.mark.asyncio
    @patch("services.scoring.network_builder.upsert_network_edge")
    async def test_skips_when_no_ownership_data(self, mock_upsert):
        session = AsyncMock()

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            sql_str = str(sql_text.text) if hasattr(sql_text, 'text') else str(sql_text)
            result_mock = MagicMock()

            if "registered_owner, ownership_data" in sql_str:
                row_mock = MagicMock()
                row_mock.get = lambda k, d=None: {
                    "registered_owner": None,
                    "ownership_data": {},
                }.get(k, d)
                mappings_mock = MagicMock()
                mappings_mock.first.return_value = row_mock
                result_mock.mappings.return_value = mappings_mock
            else:
                result_mock.all.return_value = []
            return result_mock

        session.execute = mock_execute
        result = await create_ownership_edges(session, 100)
        assert result == 0
        mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    @patch("services.scoring.network_builder.upsert_network_edge")
    async def test_skips_when_vessel_not_found(self, mock_upsert):
        session = AsyncMock()

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            result_mock = MagicMock()
            mappings_mock = MagicMock()
            mappings_mock.first.return_value = None
            result_mock.mappings.return_value = mappings_mock
            return result_mock

        session.execute = mock_execute
        result = await create_ownership_edges(session, 999)
        assert result == 0
        mock_upsert.assert_not_called()
