"""Tests for the health and stats endpoints (Story 6).

Tests cover:
- GET /api/health returns 200 when all services healthy
- GET /api/health returns 503 when database is down
- GET /api/health includes all required fields
- GET /api/stats returns correct vessel count by tier
- GET /api/stats includes ingestion rate from Redis metrics
- GET /api/stats includes anomalies by severity
- GET /api/stats includes dark ship candidate count
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import the api-server main module explicitly by file path to avoid
# collision with services/ais-ingest/main.py when the full test suite runs.
# ---------------------------------------------------------------------------
_API_SERVER_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "services", "api-server")
)
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

_API_MAIN_PATH = os.path.join(_API_SERVER_DIR, "main.py")
_spec = importlib.util.spec_from_file_location("api_server_main_health", _API_MAIN_PATH)
api_main = importlib.util.module_from_spec(_spec)
sys.modules["api_server_main_health"] = api_main
_spec.loader.exec_module(api_main)


def _make_mock_session(query_results: dict | None = None):
    """Create a mock async session that returns pre-configured query results.

    query_results maps SQL substrings to result values:
      {"SELECT 1": scalar_value, "risk_tier": [row_mappings], ...}
    """
    if query_results is None:
        query_results = {}

    mock_session = AsyncMock()

    async def execute_side_effect(stmt, *args, **kwargs):
        sql = str(stmt.text) if hasattr(stmt, "text") else str(stmt)

        result_mock = MagicMock()

        # Check which query is being run and return the appropriate result
        for key, value in query_results.items():
            if key in sql:
                if isinstance(value, list):
                    result_mock.mappings.return_value.all.return_value = value
                elif isinstance(value, Exception):
                    raise value
                else:
                    result_mock.scalar.return_value = value
                return result_mock

        # Default: return 0 for scalar, empty list for mappings
        result_mock.scalar.return_value = 0
        result_mock.mappings.return_value.all.return_value = []
        return result_mock

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)
    return mock_session


class _FakeSessionFactory:
    """A fake session factory that acts as both callable and async context manager."""

    def __init__(self, mock_session):
        self._session = mock_session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        pass


@pytest.fixture()
def _mock_deps():
    """Mock database and Redis for health/stats endpoint testing."""
    mock_engine = MagicMock()
    mock_engine.url = MagicMock()
    mock_engine.url.database = "test_db"

    mock_redis = AsyncMock()
    mock_redis.close = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=None)

    with (
        patch.object(api_main, "get_engine", return_value=mock_engine),
        patch.object(api_main, "dispose_engine", new_callable=AsyncMock),
        patch.object(api_main, "aioredis") as mock_aioredis,
    ):
        mock_aioredis.from_url.return_value = mock_redis
        yield {
            "engine": mock_engine,
            "redis": mock_redis,
            "aioredis": mock_aioredis,
        }


def _patch_get_session(mock_factory):
    """Patch get_session in the routes.health module (as imported by the app)."""
    return patch("routes.health.get_session", return_value=mock_factory)


class TestHealthEndpoint:
    """Test GET /api/health."""

    def test_health_returns_200_when_all_healthy(self, _mock_deps):
        """GET /api/health returns 200 with all services connected."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session({
            "SELECT 1": 1,
            "vessel_profiles": 42,
            "anomaly_events": 5,
        })
        mock_factory = _FakeSessionFactory(mock_session)

        now_iso = datetime.now(timezone.utc).isoformat()
        _mock_deps["redis"].get = AsyncMock(side_effect=lambda key: {
            "heimdal:metrics:last_message_at": now_iso,
        }.get(key))

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["database"] is True
        assert body["redis"] is True
        assert body["ais_connected"] is True
        assert body["last_position_timestamp"] == now_iso
        assert body["vessel_count"] == 42
        assert body["anomaly_count"] == 5

    def test_health_returns_503_when_db_down(self, _mock_deps):
        """GET /api/health returns 503 when database connectivity fails."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session({"SELECT 1": ConnectionError("DB down")})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/health")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["database"] is False

    def test_health_returns_503_when_redis_down(self, _mock_deps):
        """GET /api/health returns 503 when Redis connectivity fails."""
        from fastapi.testclient import TestClient

        _mock_deps["redis"].ping = AsyncMock(side_effect=ConnectionError("Redis down"))

        mock_session = _make_mock_session({"SELECT 1": 1})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/health")

        assert resp.status_code == 503
        body = resp.json()
        assert body["redis"] is False

    def test_health_ais_disconnected_when_stale(self, _mock_deps):
        """AIS is marked disconnected when last message is older than 120s."""
        from fastapi.testclient import TestClient

        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        _mock_deps["redis"].get = AsyncMock(side_effect=lambda key: {
            "heimdal:metrics:last_message_at": old_ts,
        }.get(key))

        mock_session = _make_mock_session({"SELECT 1": 1})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["ais_connected"] is False

    def test_health_includes_all_required_fields(self, _mock_deps):
        """Response includes all fields specified in the acceptance criteria."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session({"SELECT 1": 1})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/health")

        body = resp.json()
        required_fields = {
            "status", "database", "redis", "ais_connected",
            "last_position_timestamp", "vessel_count", "anomaly_count",
        }
        assert required_fields.issubset(body.keys()), (
            f"Missing fields: {required_fields - body.keys()}"
        )


class TestStatsEndpoint:
    """Test GET /api/stats."""

    def test_stats_returns_correct_vessel_count_by_tier(self, _mock_deps):
        """GET /api/stats returns breakdown by risk tier (green/yellow/red)."""
        from fastapi.testclient import TestClient

        tier_rows = [
            {"risk_tier": "green", "cnt": 100},
            {"risk_tier": "yellow", "cnt": 25},
            {"risk_tier": "red", "cnt": 7},
        ]

        mock_session = _make_mock_session({
            "risk_tier": tier_rows,
            "anomaly_events": [],
            "sar_detections": 3,
            "vessel_positions": 10000,
        })
        mock_factory = _FakeSessionFactory(mock_session)

        _mock_deps["redis"].get = AsyncMock(return_value=None)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_vessels"] == 132
        assert body["vessels_by_risk_tier"]["green"] == 100
        assert body["vessels_by_risk_tier"]["yellow"] == 25
        assert body["vessels_by_risk_tier"]["red"] == 7

    def test_stats_includes_ingestion_rate_from_redis(self, _mock_deps):
        """GET /api/stats includes ingestion rate read from Redis."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session({
            "risk_tier": [],
            "anomaly_events": [],
            "sar_detections": 0,
        })
        mock_factory = _FakeSessionFactory(mock_session)

        _mock_deps["redis"].get = AsyncMock(side_effect=lambda key: {
            "heimdal:metrics:ingest_rate": "42.5",
        }.get(key))

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["ingestion_rate"] == 42.5

    def test_stats_includes_anomalies_by_severity(self, _mock_deps):
        """GET /api/stats includes active anomalies broken down by severity."""
        from fastapi.testclient import TestClient

        anomaly_rows = [
            {"severity": "critical", "cnt": 2},
            {"severity": "high", "cnt": 5},
            {"severity": "moderate", "cnt": 12},
        ]

        mock_session = _make_mock_session({
            "risk_tier": [],
            "severity": anomaly_rows,
            "sar_detections": 0,
        })
        mock_factory = _FakeSessionFactory(mock_session)

        _mock_deps["redis"].get = AsyncMock(return_value=None)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["active_anomalies_by_severity"]["critical"] == 2
        assert body["active_anomalies_by_severity"]["high"] == 5
        assert body["active_anomalies_by_severity"]["moderate"] == 12

    def test_stats_includes_dark_ship_count(self, _mock_deps):
        """GET /api/stats includes dark ship candidate count."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session({
            "risk_tier": [],
            "anomaly_events": [],
            "sar_detections": 17,
        })
        mock_factory = _FakeSessionFactory(mock_session)

        _mock_deps["redis"].get = AsyncMock(return_value=None)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["dark_ship_candidates"] == 17

    def test_stats_includes_all_required_fields(self, _mock_deps):
        """Response includes all fields specified in the acceptance criteria."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session({
            "risk_tier": [],
            "anomaly_events": [],
            "sar_detections": 0,
        })
        mock_factory = _FakeSessionFactory(mock_session)
        _mock_deps["redis"].get = AsyncMock(return_value=None)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/stats")

        body = resp.json()
        required_fields = {
            "total_vessels", "vessels_by_risk_tier",
            "active_anomalies_by_severity", "dark_ship_candidates",
            "ingestion_rate", "storage_estimate",
        }
        assert required_fields.issubset(body.keys()), (
            f"Missing fields: {required_fields - body.keys()}"
        )

    def test_stats_ingestion_rate_null_when_no_redis_data(self, _mock_deps):
        """Ingestion rate is null when Redis has no data for the key."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session({
            "risk_tier": [],
            "anomaly_events": [],
            "sar_detections": 0,
        })
        mock_factory = _FakeSessionFactory(mock_session)
        _mock_deps["redis"].get = AsyncMock(return_value=None)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/stats")

        assert resp.json()["ingestion_rate"] is None
