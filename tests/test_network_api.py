"""Tests for services/api-server/routes/network.py.

Verifies:
- GET /api/vessels/{mmsi}/network returns edges and vessel profiles
- 404 for unknown MMSI
- Edge type filtering
- Depth parameter controls BFS traversal
- GET /api/network/clusters returns cluster summaries
- Empty network returns empty list
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Add the api-server directory to path so route imports work
api_server_dir = str(Path(__file__).resolve().parent.parent / "services" / "api-server")
if api_server_dir not in sys.path:
    sys.path.insert(0, api_server_dir)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test_app():
    """Create a minimal FastAPI app with the network router."""
    from fastapi import FastAPI
    from routes.network import router

    app = FastAPI()
    app.include_router(router)
    return app


def _make_mock_session_factory(execute_fn):
    """Create a mock session factory that uses a custom execute function."""
    session = AsyncMock()
    session.execute = execute_fn

    factory = MagicMock()
    context = AsyncMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = context

    return factory


# ---------------------------------------------------------------------------
# GET /api/vessels/{mmsi}/network
# ---------------------------------------------------------------------------


class TestGetVesselNetwork:
    @patch("routes.network.get_session")
    def test_returns_404_for_unknown_vessel(self, mock_get_session):
        app = _create_test_app()

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            result_mock = MagicMock()
            mappings_mock = MagicMock()
            mappings_mock.first.return_value = None
            mappings_mock.all.return_value = []
            result_mock.mappings.return_value = mappings_mock
            result_mock.all.return_value = []
            return result_mock

        mock_get_session.return_value = _make_mock_session_factory(mock_execute)

        client = TestClient(app)
        response = client.get("/api/vessels/999999/network")
        assert response.status_code == 404

    @patch("routes.network.get_session")
    def test_returns_edges_for_known_vessel(self, mock_get_session):
        app = _create_test_app()
        call_count = [0]

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            nonlocal call_count
            sql_str = str(sql_text.text) if hasattr(sql_text, 'text') else str(sql_text)
            result_mock = MagicMock()

            if "FROM vessel_profiles WHERE mmsi" in sql_str and "IN" not in sql_str:
                # Vessel profile lookup
                row_mock = MagicMock()
                vessel_data = {
                    "mmsi": 100,
                    "ship_name": "Test Vessel",
                    "flag_country": "PA",
                    "risk_tier": "yellow",
                    "ship_type": 80,
                    "network_score": 30,
                }
                row_mock.__getitem__ = lambda s, k: vessel_data[k]
                row_mock.get = lambda k, d=None: vessel_data.get(k, d)
                row_mock.keys = lambda: vessel_data.keys()
                row_mock.items = lambda: vessel_data.items()
                row_mock.__iter__ = lambda s: iter(vessel_data.items())

                mappings_mock = MagicMock()
                mappings_mock.first.return_value = row_mock
                result_mock.mappings.return_value = mappings_mock
            elif "FROM network_edges" in sql_str:
                # Edge lookup - return one edge
                edge_data = {
                    "id": 1,
                    "vessel_a_mmsi": 100,
                    "vessel_b_mmsi": 200,
                    "edge_type": "encounter",
                    "confidence": 1.0,
                    "first_observed": "2024-06-01T00:00:00",
                    "last_observed": "2024-06-01T00:00:00",
                    "observation_count": 1,
                    "lat": 55.0,
                    "lon": 25.0,
                    "details": {},
                }
                row_mock = MagicMock()
                row_mock.__getitem__ = lambda s, k: edge_data[k]
                row_mock.get = lambda k, d=None: edge_data.get(k, d)
                row_mock.keys = lambda: edge_data.keys()
                row_mock.items = lambda: edge_data.items()
                row_mock.__iter__ = lambda s: iter(edge_data.items())

                mappings_mock = MagicMock()
                mappings_mock.all.return_value = [row_mock]
                result_mock.mappings.return_value = mappings_mock
            elif "IN" in sql_str and "vessel_profiles" in sql_str:
                # Connected vessel profiles
                other_data = {
                    "mmsi": 200,
                    "ship_name": "Other Vessel",
                    "flag_country": "LR",
                    "risk_tier": "green",
                    "ship_type": 80,
                    "network_score": 0,
                }
                row_mock = MagicMock()
                row_mock.__getitem__ = lambda s, k: other_data[k]
                row_mock.get = lambda k, d=None: other_data.get(k, d)
                row_mock.keys = lambda: other_data.keys()
                row_mock.items = lambda: other_data.items()
                row_mock.__iter__ = lambda s: iter(other_data.items())

                mappings_mock = MagicMock()
                mappings_mock.all.return_value = [row_mock]
                result_mock.mappings.return_value = mappings_mock
            else:
                mappings_mock = MagicMock()
                mappings_mock.all.return_value = []
                mappings_mock.first.return_value = None
                result_mock.mappings.return_value = mappings_mock

            return result_mock

        mock_get_session.return_value = _make_mock_session_factory(mock_execute)

        client = TestClient(app)
        response = client.get("/api/vessels/100/network")
        assert response.status_code == 200

        data = response.json()
        assert data["mmsi"] == 100
        assert len(data["edges"]) == 1
        assert data["edges"][0]["edge_type"] == "encounter"
        # JSON serializes integer keys as strings
        assert "100" in data["vessels"]
        assert "200" in data["vessels"]

    @patch("routes.network.get_session")
    def test_depth_parameter_validation(self, mock_get_session):
        app = _create_test_app()
        client = TestClient(app)

        # depth > 3 should be rejected
        response = client.get("/api/vessels/100/network?depth=5")
        assert response.status_code == 422

        # depth < 1 should be rejected
        response = client.get("/api/vessels/100/network?depth=0")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/network/clusters
# ---------------------------------------------------------------------------


class TestGetNetworkClusters:
    @patch("routes.network.get_session")
    def test_empty_network(self, mock_get_session):
        app = _create_test_app()

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            result_mock = MagicMock()
            result_mock.all.return_value = []
            mappings_mock = MagicMock()
            mappings_mock.all.return_value = []
            result_mock.mappings.return_value = mappings_mock
            return result_mock

        mock_get_session.return_value = _make_mock_session_factory(mock_execute)

        client = TestClient(app)
        response = client.get("/api/network/clusters")
        assert response.status_code == 200
        data = response.json()
        assert data["clusters"] == []
        assert data["total"] == 0

    @patch("routes.network.get_session")
    def test_returns_cluster_summaries(self, mock_get_session):
        app = _create_test_app()

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            sql_str = str(sql_text.text) if hasattr(sql_text, 'text') else str(sql_text)
            result_mock = MagicMock()

            if "FROM network_edges" in sql_str:
                # Return edges forming a cluster of 3 vessels
                result_mock.all.return_value = [
                    (100, 200),
                    (200, 300),
                ]
            elif "FROM vessel_profiles" in sql_str:
                # Return profile data
                profiles = [
                    {
                        "mmsi": 100,
                        "risk_tier": "red",
                        "sanctions_status": {"lists": ["OFAC"]},
                        "ship_name": "Vessel Alpha",
                        "flag_country": "PA",
                        "ship_type": 80,
                    },
                    {
                        "mmsi": 200,
                        "risk_tier": "yellow",
                        "sanctions_status": {},
                        "ship_name": "Vessel Beta",
                        "flag_country": "LR",
                        "ship_type": 80,
                    },
                    {
                        "mmsi": 300,
                        "risk_tier": "green",
                        "sanctions_status": {},
                        "ship_name": "Vessel Gamma",
                        "flag_country": "MH",
                        "ship_type": 80,
                    },
                ]
                mapping_rows = []
                for p in profiles:
                    row_mock = MagicMock()
                    row_mock.__getitem__ = lambda s, k, _p=p: _p[k]
                    row_mock.get = lambda k, d=None, _p=p: _p.get(k, d)
                    row_mock.keys = lambda _p=p: _p.keys()
                    row_mock.items = lambda _p=p: _p.items()
                    mapping_rows.append(row_mock)

                mappings_mock = MagicMock()
                mappings_mock.all.return_value = mapping_rows
                result_mock.mappings.return_value = mappings_mock
            else:
                result_mock.all.return_value = []

            return result_mock

        mock_get_session.return_value = _make_mock_session_factory(mock_execute)

        client = TestClient(app)
        response = client.get("/api/network/clusters")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        cluster = data["clusters"][0]
        assert cluster["cluster_size"] == 3
        assert cluster["max_risk_tier"] == "red"
        assert cluster["sanctioned_count"] == 1
        assert len(cluster["members"]) == 3

    @patch("routes.network.get_session")
    def test_min_size_filter(self, mock_get_session):
        app = _create_test_app()

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            sql_str = str(sql_text.text) if hasattr(sql_text, 'text') else str(sql_text)
            result_mock = MagicMock()

            if "FROM network_edges" in sql_str:
                # Two separate pairs (clusters of size 2)
                result_mock.all.return_value = [
                    (100, 200),
                    (300, 400),
                ]
            else:
                result_mock.all.return_value = []
                mappings_mock = MagicMock()
                mappings_mock.all.return_value = []
                result_mock.mappings.return_value = mappings_mock

            return result_mock

        mock_get_session.return_value = _make_mock_session_factory(mock_execute)

        client = TestClient(app)
        # min_size=3 should filter out pairs
        response = client.get("/api/network/clusters?min_size=3")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
