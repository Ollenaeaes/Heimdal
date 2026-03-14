"""Tests for services/api-server/routes/gnss_zones.py.

Verifies:
- GET /api/gnss-zones returns GeoJSON FeatureCollection
- Only non-expired zones are returned
- Empty table returns empty features
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Add the api-server directory to path so route imports work
api_server_dir = str(Path(__file__).resolve().parent.parent / "services" / "api-server")
if api_server_dir not in sys.path:
    sys.path.insert(0, api_server_dir)


def _create_test_app():
    """Create a minimal FastAPI app with the gnss_zones router."""
    from fastapi import FastAPI
    from routes.gnss_zones import router

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


class TestGetGnssZones:
    @patch("routes.gnss_zones.get_session")
    def test_returns_geojson_feature_collection(self, mock_get_session):
        app = _create_test_app()

        now = datetime.now(timezone.utc)
        future = now + timedelta(hours=6)

        zone_data = {
            "id": 1,
            "detected_at": now,
            "expires_at": future,
            "affected_count": 5,
            "details": {"source": "gnss_cluster"},
            "geojson": json.dumps({
                "type": "Polygon",
                "coordinates": [[[25.0, 55.0], [26.0, 55.0], [26.0, 56.0], [25.0, 56.0], [25.0, 55.0]]],
            }),
        }
        row_mock = MagicMock()
        row_mock.__getitem__ = lambda s, k: zone_data[k]
        row_mock.get = lambda k, d=None: zone_data.get(k, d)

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            result_mock = MagicMock()
            mappings_mock = MagicMock()
            mappings_mock.all.return_value = [row_mock]
            result_mock.mappings.return_value = mappings_mock
            return result_mock

        mock_get_session.return_value = _make_mock_session_factory(mock_execute)

        client = TestClient(app)
        response = client.get("/api/gnss-zones")
        assert response.status_code == 200

        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 1

        feature = data["features"][0]
        assert feature["type"] == "Feature"
        assert feature["properties"]["id"] == 1
        assert feature["properties"]["affected_count"] == 5
        assert feature["geometry"]["type"] == "Polygon"
        assert len(feature["geometry"]["coordinates"][0]) == 5

    @patch("routes.gnss_zones.get_session")
    def test_empty_table_returns_empty_features(self, mock_get_session):
        app = _create_test_app()

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            result_mock = MagicMock()
            mappings_mock = MagicMock()
            mappings_mock.all.return_value = []
            result_mock.mappings.return_value = mappings_mock
            return result_mock

        mock_get_session.return_value = _make_mock_session_factory(mock_execute)

        client = TestClient(app)
        response = client.get("/api/gnss-zones")
        assert response.status_code == 200

        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert data["features"] == []

    @patch("routes.gnss_zones.get_session")
    def test_sql_filters_by_expires_at(self, mock_get_session):
        """Verify the SQL query includes WHERE expires_at > NOW()."""
        app = _create_test_app()
        captured_sql = []

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            sql_str = str(sql_text.text) if hasattr(sql_text, 'text') else str(sql_text)
            captured_sql.append(sql_str)
            result_mock = MagicMock()
            mappings_mock = MagicMock()
            mappings_mock.all.return_value = []
            result_mock.mappings.return_value = mappings_mock
            return result_mock

        mock_get_session.return_value = _make_mock_session_factory(mock_execute)

        client = TestClient(app)
        response = client.get("/api/gnss-zones")
        assert response.status_code == 200

        # Verify the SQL filters for non-expired zones
        assert len(captured_sql) == 1
        assert "expires_at > NOW()" in captured_sql[0]

    @patch("routes.gnss_zones.get_session")
    def test_multiple_zones_returned(self, mock_get_session):
        app = _create_test_app()

        now = datetime.now(timezone.utc)
        future = now + timedelta(hours=6)

        zones = []
        for i in range(3):
            zone = {
                "id": i + 1,
                "detected_at": now,
                "expires_at": future,
                "affected_count": 3 + i * 2,
                "details": {},
                "geojson": json.dumps({
                    "type": "Polygon",
                    "coordinates": [[[25.0 + i, 55.0], [26.0 + i, 55.0], [26.0 + i, 56.0], [25.0 + i, 56.0], [25.0 + i, 55.0]]],
                }),
            }
            row_mock = MagicMock()
            row_mock.__getitem__ = lambda s, k, _z=zone: _z[k]
            row_mock.get = lambda k, d=None, _z=zone: _z.get(k, d)
            zones.append(row_mock)

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            result_mock = MagicMock()
            mappings_mock = MagicMock()
            mappings_mock.all.return_value = zones
            result_mock.mappings.return_value = mappings_mock
            return result_mock

        mock_get_session.return_value = _make_mock_session_factory(mock_execute)

        client = TestClient(app)
        response = client.get("/api/gnss-zones")
        assert response.status_code == 200

        data = response.json()
        assert len(data["features"]) == 3
        assert data["features"][0]["properties"]["affected_count"] == 3
        assert data["features"][2]["properties"]["affected_count"] == 7
