"""Tests for the API server app factory, lifespan, and health endpoint."""

from __future__ import annotations

import importlib.util
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import the api-server main module explicitly by file path to avoid
# collision with services/ais-ingest/main.py when the full test suite runs.
# ---------------------------------------------------------------------------
_API_MAIN_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "services", "api-server", "main.py")
)
_spec = importlib.util.spec_from_file_location("api_server_main", _API_MAIN_PATH)
api_main = importlib.util.module_from_spec(_spec)
sys.modules["api_server_main"] = api_main
_spec.loader.exec_module(api_main)


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


def _make_simple_mock_session():
    """Create a mock session that returns sensible defaults for health queries."""
    mock_session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar.return_value = 0
    result_mock.mappings.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=result_mock)
    return mock_session


@pytest.fixture()
def _mock_dependencies():
    """Mock database and Redis so the app can start without real services."""
    mock_engine = MagicMock()
    mock_engine.url = MagicMock()
    mock_engine.url.database = "test_db"

    mock_redis = AsyncMock()
    mock_redis.close = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=None)

    mock_session = _make_simple_mock_session()
    mock_factory = _FakeSessionFactory(mock_session)

    with (
        patch.object(api_main, "get_engine", return_value=mock_engine) as _engine,
        patch.object(api_main, "dispose_engine", new_callable=AsyncMock) as _dispose,
        patch.object(api_main, "aioredis") as mock_aioredis,
        patch("routes.health.get_session", return_value=mock_factory),
    ):
        mock_aioredis.from_url.return_value = mock_redis
        yield {
            "engine": mock_engine,
            "dispose_engine": _dispose,
            "redis": mock_redis,
            "aioredis": mock_aioredis,
        }


class TestAppStartup:
    """Test that the app starts and shuts down correctly."""

    def test_app_starts_without_errors(self, _mock_dependencies):
        """App should start successfully when database and Redis are available."""
        from fastapi.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            response = client.get("/api/health")
            assert response.status_code == 200

        # Verify shutdown closed Redis and disposed engine
        _mock_dependencies["redis"].close.assert_awaited_once()
        _mock_dependencies["dispose_engine"].assert_awaited_once()

    def test_redis_stored_on_app_state(self, _mock_dependencies):
        """Redis client should be stored on app.state during lifespan."""
        from fastapi.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app):
            assert app.state.redis is _mock_dependencies["redis"]

    def test_redis_connected_with_settings_url(self, _mock_dependencies):
        """Redis should be connected using the URL from settings."""
        from fastapi.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app):
            _mock_dependencies["aioredis"].from_url.assert_called_once()
            call_args = _mock_dependencies["aioredis"].from_url.call_args
            assert "redis://" in call_args[0][0]
            assert call_args[1]["decode_responses"] is True


class TestHealthEndpoint:
    """Test the health check endpoint."""

    def test_health_returns_ok(self, _mock_dependencies):
        """GET /api/health should return 200 with status ok."""
        from fastapi.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            response = client.get("/api/health")
            assert response.status_code == 200
            assert response.json()["status"] == "ok"

    def test_health_responds_immediately(self, _mock_dependencies):
        """Health endpoint should respond quickly (< 1 second)."""
        from fastapi.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            start = time.monotonic()
            response = client.get("/api/health")
            elapsed = time.monotonic() - start

            assert response.status_code == 200
            assert elapsed < 1.0, f"Health check took {elapsed:.2f}s, expected < 1s"


class TestCorsMiddleware:
    """Test that CORS is configured for local development."""

    def test_cors_allows_any_origin(self, _mock_dependencies):
        """CORS should allow requests from any origin in dev mode."""
        from fastapi.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            response = client.options(
                "/api/health",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert response.headers.get("access-control-allow-origin") in (
                "*",
                "http://localhost:3000",
            )


class TestAppFactory:
    """Test the create_app factory function."""

    def test_creates_fastapi_instance(self, _mock_dependencies):
        """create_app should return a FastAPI instance."""
        from fastapi import FastAPI

        app = api_main.create_app()
        assert isinstance(app, FastAPI)

    def test_app_title(self, _mock_dependencies):
        """App should have the correct title."""
        app = api_main.create_app()
        assert app.title == "Heimdal API"
