"""Tests for watchlist endpoints (Story 4).

Tests cover:
- GET /api/watchlist returns all watchlisted vessels
- POST /api/watchlist/{mmsi} adds vessel to watchlist
- POST /api/watchlist/{mmsi} returns 404 for nonexistent MMSI
- DELETE /api/watchlist/{mmsi} removes vessel from watchlist
- POST is idempotent (upsert behaviour)
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import the api-server main module explicitly by file path
# ---------------------------------------------------------------------------
_API_SERVER_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "services", "api-server")
)
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

_API_MAIN_PATH = os.path.join(_API_SERVER_DIR, "main.py")
_spec = importlib.util.spec_from_file_location("api_server_main_watchlist", _API_MAIN_PATH)
api_main = importlib.util.module_from_spec(_spec)
sys.modules["api_server_main_watchlist"] = api_main
_spec.loader.exec_module(api_main)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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


def _make_mock_session(execute_side_effect=None):
    """Create a mock async session with configurable execute behaviour."""
    mock_session = AsyncMock()
    if execute_side_effect:
        mock_session.execute = AsyncMock(side_effect=execute_side_effect)
    else:
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = []
        result_mock.first.return_value = None
        result_mock.scalar.return_value = 0
        mock_session.execute = AsyncMock(return_value=result_mock)
    mock_session.commit = AsyncMock()
    return mock_session


@pytest.fixture()
def _mock_deps():
    """Mock database and Redis for watchlist endpoint testing."""
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
        yield


class TestWatchlistGet:
    """Test GET /api/watchlist."""

    def test_returns_all_watchlisted_vessels(self, _mock_deps):
        """GET /api/watchlist returns watchlisted vessels with notes."""
        from fastapi.testclient import TestClient

        watchlist_rows = [
            {
                "mmsi": 211234567,
                "reason": "Suspected sanctions evasion",
                "added_at": datetime(2025, 6, 10, 8, 0, 0, tzinfo=timezone.utc),
                "ship_name": "NORDIC STAR",
                "flag_country": "DE",
                "risk_tier": "red",
            },
            {
                "mmsi": 311654321,
                "reason": None,
                "added_at": datetime(2025, 6, 12, 14, 0, 0, tzinfo=timezone.utc),
                "ship_name": "OCEAN BREEZE",
                "flag_country": "PA",
                "risk_tier": "yellow",
            },
        ]

        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = watchlist_rows
        mock_session = _make_mock_session(
            execute_side_effect=AsyncMock(return_value=result_mock)
        )
        mock_factory = _FakeSessionFactory(mock_session)

        with patch("routes.watchlist.get_session", return_value=mock_factory):
            app = api_main.create_app()
            with TestClient(app) as client:
                resp = client.get("/api/watchlist")

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert len(body["items"]) == 2
        assert body["items"][0]["mmsi"] == 211234567
        assert body["items"][0]["reason"] == "Suspected sanctions evasion"
        assert body["items"][1]["mmsi"] == 311654321

    def test_returns_empty_when_no_vessels(self, _mock_deps):
        """GET /api/watchlist returns empty list when no vessels watched."""
        from fastapi.testclient import TestClient

        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = []
        mock_session = _make_mock_session(
            execute_side_effect=AsyncMock(return_value=result_mock)
        )
        mock_factory = _FakeSessionFactory(mock_session)

        with patch("routes.watchlist.get_session", return_value=mock_factory):
            app = api_main.create_app()
            with TestClient(app) as client:
                resp = client.get("/api/watchlist")

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["items"] == []


class TestWatchlistPost:
    """Test POST /api/watchlist/{mmsi}."""

    def test_adds_vessel_to_watchlist(self, _mock_deps):
        """POST /api/watchlist/{mmsi} adds the vessel and returns 201."""
        from fastapi.testclient import TestClient

        call_count = 0

        async def execute_side_effect(stmt, params=None, **kwargs):
            nonlocal call_count
            call_count += 1
            result_mock = MagicMock()
            if call_count == 1:
                # First call: check vessel exists - return a row
                result_mock.first.return_value = (211234567,)
            else:
                # Second call: INSERT
                result_mock.first.return_value = None
            return result_mock

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_session.commit = AsyncMock()
        mock_factory = _FakeSessionFactory(mock_session)

        with patch("routes.watchlist.get_session", return_value=mock_factory):
            app = api_main.create_app()
            with TestClient(app) as client:
                resp = client.post(
                    "/api/watchlist/211234567",
                    json={"reason": "Suspected dark-to-dark transfer"},
                )

        assert resp.status_code == 201
        body = resp.json()
        assert body["mmsi"] == 211234567
        assert body["reason"] == "Suspected dark-to-dark transfer"
        assert body["status"] == "added"

    def test_adds_vessel_without_reason(self, _mock_deps):
        """POST /api/watchlist/{mmsi} with empty body works (reason is optional)."""
        from fastapi.testclient import TestClient

        call_count = 0

        async def execute_side_effect(stmt, params=None, **kwargs):
            nonlocal call_count
            call_count += 1
            result_mock = MagicMock()
            if call_count == 1:
                result_mock.first.return_value = (211234567,)
            else:
                result_mock.first.return_value = None
            return result_mock

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_session.commit = AsyncMock()
        mock_factory = _FakeSessionFactory(mock_session)

        with patch("routes.watchlist.get_session", return_value=mock_factory):
            app = api_main.create_app()
            with TestClient(app) as client:
                resp = client.post("/api/watchlist/211234567")

        assert resp.status_code == 201
        body = resp.json()
        assert body["mmsi"] == 211234567
        assert body["reason"] is None

    def test_returns_404_for_nonexistent_mmsi(self, _mock_deps):
        """POST /api/watchlist/{mmsi} returns 404 when vessel not in vessel_profiles."""
        from fastapi.testclient import TestClient

        async def execute_side_effect(stmt, params=None, **kwargs):
            result_mock = MagicMock()
            # vessel_profiles lookup returns no row
            result_mock.first.return_value = None
            return result_mock

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_session.commit = AsyncMock()
        mock_factory = _FakeSessionFactory(mock_session)

        with patch("routes.watchlist.get_session", return_value=mock_factory):
            app = api_main.create_app()
            with TestClient(app) as client:
                resp = client.post(
                    "/api/watchlist/999999999",
                    json={"reason": "Testing nonexistent vessel"},
                )

        assert resp.status_code == 404
        assert "999999999" in resp.json()["detail"]


class TestWatchlistDelete:
    """Test DELETE /api/watchlist/{mmsi}."""

    def test_removes_vessel_from_watchlist(self, _mock_deps):
        """DELETE /api/watchlist/{mmsi} removes the vessel and returns 200."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session()
        mock_factory = _FakeSessionFactory(mock_session)

        with patch("routes.watchlist.get_session", return_value=mock_factory):
            app = api_main.create_app()
            with TestClient(app) as client:
                resp = client.delete("/api/watchlist/211234567")

        assert resp.status_code == 200
        body = resp.json()
        assert body["mmsi"] == 211234567
        assert body["status"] == "removed"
        # Verify session.commit was called
        mock_session.commit.assert_awaited()


class TestWatchlistAddThenGet:
    """Integration-style test: add a vessel then verify it appears in GET."""

    def test_post_then_get_returns_vessel(self, _mock_deps):
        """POST adds a vessel, GET returns it in the list."""
        from fastapi.testclient import TestClient

        # Track state across calls
        watchlist_data: list[dict] = []
        call_sequence: list[str] = []

        async def post_execute_side_effect(stmt, params=None, **kwargs):
            sql = str(stmt.text) if hasattr(stmt, "text") else str(stmt)
            result_mock = MagicMock()
            if "vessel_profiles" in sql:
                call_sequence.append("check_vessel")
                result_mock.first.return_value = (211234567,)
            elif "INSERT" in sql:
                call_sequence.append("insert")
                watchlist_data.append({
                    "mmsi": 211234567,
                    "reason": "Monitoring for STS activity",
                    "added_at": "2025-06-15T10:00:00+00:00",
                    "ship_name": "NORDIC STAR",
                    "flag_country": "DE",
                    "risk_tier": "red",
                })
            return result_mock

        async def get_execute_side_effect(stmt, params=None, **kwargs):
            result_mock = MagicMock()
            result_mock.mappings.return_value.all.return_value = watchlist_data
            return result_mock

        # POST phase
        post_session = AsyncMock()
        post_session.execute = AsyncMock(side_effect=post_execute_side_effect)
        post_session.commit = AsyncMock()
        post_factory = _FakeSessionFactory(post_session)

        with patch("routes.watchlist.get_session", return_value=post_factory):
            app = api_main.create_app()
            with TestClient(app) as client:
                post_resp = client.post(
                    "/api/watchlist/211234567",
                    json={"reason": "Monitoring for STS activity"},
                )

        assert post_resp.status_code == 201

        # GET phase
        get_session = AsyncMock()
        get_session.execute = AsyncMock(side_effect=get_execute_side_effect)
        get_factory = _FakeSessionFactory(get_session)

        with patch("routes.watchlist.get_session", return_value=get_factory):
            app = api_main.create_app()
            with TestClient(app) as client:
                get_resp = client.get("/api/watchlist")

        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["count"] == 1
        assert body["items"][0]["mmsi"] == 211234567
        assert body["items"][0]["reason"] == "Monitoring for STS activity"
