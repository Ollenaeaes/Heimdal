"""Tests for services/api-server/routes/infrastructure.py.

Verifies:
- GET /api/infrastructure/routes returns GeoJSON FeatureCollection
- GET /api/infrastructure/alerts returns sorted alerts
- Empty data returns proper empty structures
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Add the api-server directory to path so route imports work
api_server_dir = str(Path(__file__).resolve().parent.parent / "services" / "api-server")
if api_server_dir not in sys.path:
    sys.path.insert(0, api_server_dir)


def _create_test_app():
    """Create a minimal FastAPI app with the infrastructure router."""
    from fastapi import FastAPI
    from routes.infrastructure import router

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


class TestGetInfrastructureRoutes:
    @patch("routes.infrastructure.get_session")
    def test_returns_geojson_feature_collection(self, mock_get_session):
        app = _create_test_app()

        route_geojson = json.dumps({
            "type": "LineString",
            "coordinates": [[5.125, 60.391], [5.234, 60.412], [5.345, 60.425]],
        })

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            result_mock = MagicMock()
            row_data = {
                "id": 1,
                "name": "Nordlink HVDC Cable",
                "route_type": "power_cable",
                "operator": "Statnett",
                "buffer_nm": 1.0,
                "geojson": route_geojson,
            }
            row_mock = MagicMock()
            row_mock.__getitem__ = lambda s, k: row_data[k]
            row_mock.get = lambda k, d=None: row_data.get(k, d)
            row_mock.keys = lambda: row_data.keys()

            mappings_mock = MagicMock()
            mappings_mock.all.return_value = [row_mock]
            result_mock.mappings.return_value = mappings_mock
            return result_mock

        mock_get_session.return_value = _make_mock_session_factory(mock_execute)

        client = TestClient(app)
        response = client.get("/api/infrastructure/routes")
        assert response.status_code == 200

        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 1

        feature = data["features"][0]
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "LineString"
        assert len(feature["geometry"]["coordinates"]) == 3
        assert feature["properties"]["id"] == 1
        assert feature["properties"]["name"] == "Nordlink HVDC Cable"
        assert feature["properties"]["route_type"] == "power_cable"
        assert feature["properties"]["operator"] == "Statnett"
        assert feature["properties"]["buffer_nm"] == 1.0

    @patch("routes.infrastructure.get_session")
    def test_empty_routes(self, mock_get_session):
        app = _create_test_app()

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            result_mock = MagicMock()
            mappings_mock = MagicMock()
            mappings_mock.all.return_value = []
            result_mock.mappings.return_value = mappings_mock
            return result_mock

        mock_get_session.return_value = _make_mock_session_factory(mock_execute)

        client = TestClient(app)
        response = client.get("/api/infrastructure/routes")
        assert response.status_code == 200

        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert data["features"] == []

    @patch("routes.infrastructure.get_session")
    def test_multiple_routes(self, mock_get_session):
        app = _create_test_app()

        routes = [
            {
                "id": 1,
                "name": "Nordlink HVDC Cable",
                "route_type": "power_cable",
                "operator": "Statnett",
                "buffer_nm": 1.0,
                "geojson": json.dumps({
                    "type": "LineString",
                    "coordinates": [[5.1, 60.3], [5.2, 60.4]],
                }),
            },
            {
                "id": 2,
                "name": "Europipe II",
                "route_type": "gas_pipeline",
                "operator": "Gassco",
                "buffer_nm": 0.5,
                "geojson": json.dumps({
                    "type": "LineString",
                    "coordinates": [[3.5, 56.0], [3.8, 56.2]],
                }),
            },
        ]

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            result_mock = MagicMock()
            row_mocks = []
            for route in routes:
                row_mock = MagicMock()
                row_mock.__getitem__ = lambda s, k, _r=route: _r[k]
                row_mock.get = lambda k, d=None, _r=route: _r.get(k, d)
                row_mock.keys = lambda _r=route: _r.keys()
                row_mocks.append(row_mock)

            mappings_mock = MagicMock()
            mappings_mock.all.return_value = row_mocks
            result_mock.mappings.return_value = mappings_mock
            return result_mock

        mock_get_session.return_value = _make_mock_session_factory(mock_execute)

        client = TestClient(app)
        response = client.get("/api/infrastructure/routes")
        assert response.status_code == 200

        data = response.json()
        assert len(data["features"]) == 2
        assert data["features"][0]["properties"]["name"] == "Nordlink HVDC Cable"
        assert data["features"][1]["properties"]["name"] == "Europipe II"


class TestGetInfrastructureAlerts:
    @patch("routes.infrastructure.get_session")
    def test_returns_sorted_alerts(self, mock_get_session):
        app = _create_test_app()

        alerts = [
            {
                "id": 1,
                "mmsi": 273456789,
                "route_id": 1,
                "entry_time": "2025-11-15T08:00:00+00:00",
                "min_speed": 2.3,
                "max_alignment": 15.0,
                "vessel_name": "Volga Spirit",
                "risk_tier": "red",
                "risk_score": 85,
                "lat": 60.42,
                "lon": 5.30,
                "route_name": "Nordlink HVDC Cable",
                "route_type": "power_cable",
            },
            {
                "id": 2,
                "mmsi": 211000001,
                "route_id": 1,
                "entry_time": "2025-11-15T09:30:00+00:00",
                "min_speed": 5.0,
                "max_alignment": 45.0,
                "vessel_name": "Baltic Trader",
                "risk_tier": "yellow",
                "risk_score": 55,
                "lat": 60.41,
                "lon": 5.25,
                "route_name": "Nordlink HVDC Cable",
                "route_type": "power_cable",
            },
        ]

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            result_mock = MagicMock()
            row_mocks = []
            for alert in alerts:
                row_mock = MagicMock()
                row_mock.__getitem__ = lambda s, k, _a=alert: _a[k]
                row_mock.get = lambda k, d=None, _a=alert: _a.get(k, d)
                row_mock.keys = lambda _a=alert: _a.keys()
                row_mocks.append(row_mock)

            mappings_mock = MagicMock()
            mappings_mock.all.return_value = row_mocks
            result_mock.mappings.return_value = mappings_mock
            return result_mock

        mock_get_session.return_value = _make_mock_session_factory(mock_execute)

        client = TestClient(app)
        response = client.get("/api/infrastructure/alerts")
        assert response.status_code == 200

        data = response.json()
        assert len(data["alerts"]) == 2
        # Sorted by risk_score DESC (API does ORDER BY)
        assert data["alerts"][0]["risk_score"] == 85
        assert data["alerts"][0]["vessel_name"] == "Volga Spirit"
        assert data["alerts"][1]["risk_score"] == 55
        assert data["alerts"][1]["vessel_name"] == "Baltic Trader"

    @patch("routes.infrastructure.get_session")
    def test_empty_alerts(self, mock_get_session):
        app = _create_test_app()

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            result_mock = MagicMock()
            mappings_mock = MagicMock()
            mappings_mock.all.return_value = []
            result_mock.mappings.return_value = mappings_mock
            return result_mock

        mock_get_session.return_value = _make_mock_session_factory(mock_execute)

        client = TestClient(app)
        response = client.get("/api/infrastructure/alerts")
        assert response.status_code == 200

        data = response.json()
        assert data["alerts"] == []

    @patch("routes.infrastructure.get_session")
    def test_alert_has_required_fields(self, mock_get_session):
        app = _create_test_app()

        alert_data = {
            "id": 1,
            "mmsi": 273456789,
            "route_id": 1,
            "entry_time": "2025-11-15T08:00:00+00:00",
            "min_speed": 2.3,
            "max_alignment": 15.0,
            "vessel_name": "Volga Spirit",
            "risk_tier": "red",
            "risk_score": 85,
            "lat": 60.42,
            "lon": 5.30,
            "route_name": "Nordlink HVDC Cable",
            "route_type": "power_cable",
        }

        async def mock_execute(sql_text, params=None, *args, **kwargs):
            result_mock = MagicMock()
            row_mock = MagicMock()
            row_mock.__getitem__ = lambda s, k: alert_data[k]
            row_mock.get = lambda k, d=None: alert_data.get(k, d)
            row_mock.keys = lambda: alert_data.keys()

            mappings_mock = MagicMock()
            mappings_mock.all.return_value = [row_mock]
            result_mock.mappings.return_value = mappings_mock
            return result_mock

        mock_get_session.return_value = _make_mock_session_factory(mock_execute)

        client = TestClient(app)
        response = client.get("/api/infrastructure/alerts")
        assert response.status_code == 200

        alert = response.json()["alerts"][0]
        assert "id" in alert
        assert "mmsi" in alert
        assert "vessel_name" in alert
        assert "risk_tier" in alert
        assert "risk_score" in alert
        assert "lat" in alert
        assert "lon" in alert
        assert "route_name" in alert
        assert "route_type" in alert
        assert "entry_time" in alert
