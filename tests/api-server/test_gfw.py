"""Tests for GFW event endpoints (Story 4).

Tests cover:
- GET /api/gfw/events returns paginated results
- GET /api/gfw/events filters by event_type
- GET /api/gfw/events filters by mmsi
- GET /api/gfw/events filters by time range (start/end)
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
_spec = importlib.util.spec_from_file_location("api_server_main_gfw", _API_MAIN_PATH)
api_main = importlib.util.module_from_spec(_spec)
sys.modules["api_server_main_gfw"] = api_main
_spec.loader.exec_module(api_main)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_SAMPLE_EVENTS = [
    {
        "id": 1,
        "gfw_event_id": "evt-001",
        "event_type": "ENCOUNTER",
        "mmsi": 211234567,
        "start_time": datetime(2025, 6, 10, 8, 0, 0, tzinfo=timezone.utc),
        "end_time": datetime(2025, 6, 10, 10, 0, 0, tzinfo=timezone.utc),
        "lat": 25.5,
        "lon": 55.3,
        "details": {},
        "encounter_mmsi": 311654321,
        "port_name": None,
        "ingested_at": datetime(2025, 6, 10, 12, 0, 0, tzinfo=timezone.utc),
    },
    {
        "id": 2,
        "gfw_event_id": "evt-002",
        "event_type": "LOITERING",
        "mmsi": 211234567,
        "start_time": datetime(2025, 6, 12, 14, 0, 0, tzinfo=timezone.utc),
        "end_time": datetime(2025, 6, 12, 18, 0, 0, tzinfo=timezone.utc),
        "lat": 26.0,
        "lon": 56.0,
        "details": {},
        "encounter_mmsi": None,
        "port_name": None,
        "ingested_at": datetime(2025, 6, 12, 20, 0, 0, tzinfo=timezone.utc),
    },
    {
        "id": 3,
        "gfw_event_id": "evt-003",
        "event_type": "ENCOUNTER",
        "mmsi": 411987654,
        "start_time": datetime(2025, 6, 14, 6, 0, 0, tzinfo=timezone.utc),
        "end_time": datetime(2025, 6, 14, 8, 0, 0, tzinfo=timezone.utc),
        "lat": 30.0,
        "lon": 50.0,
        "details": {},
        "encounter_mmsi": 511111111,
        "port_name": None,
        "ingested_at": datetime(2025, 6, 14, 10, 0, 0, tzinfo=timezone.utc),
    },
]


@pytest.fixture()
def _mock_deps():
    """Mock database and Redis for GFW endpoint testing."""
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


class TestGfwEvents:
    """Test GET /api/gfw/events."""

    def test_returns_paginated_results(self, _mock_deps):
        """GET /api/gfw/events returns items with count, limit, offset."""
        from fastapi.testclient import TestClient

        with patch(
            "routes.gfw.list_gfw_events",
            new_callable=AsyncMock,
            return_value=_SAMPLE_EVENTS,
        ):
            app = api_main.create_app()
            with TestClient(app) as client:
                resp = client.get("/api/gfw/events")

        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert body["count"] == 3
        assert body["limit"] == 100
        assert body["offset"] == 0

    def test_filters_by_event_type(self, _mock_deps):
        """GET /api/gfw/events?event_type=ENCOUNTER returns only encounter events."""
        from fastapi.testclient import TestClient

        encounters = [e for e in _SAMPLE_EVENTS if e["event_type"] == "ENCOUNTER"]

        with patch(
            "routes.gfw.list_gfw_events",
            new_callable=AsyncMock,
            return_value=encounters,
        ) as mock_list:
            app = api_main.create_app()
            with TestClient(app) as client:
                resp = client.get("/api/gfw/events?event_type=ENCOUNTER")

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        for item in body["items"]:
            assert item["event_type"] == "ENCOUNTER"

        call_kwargs = mock_list.call_args
        assert call_kwargs[1]["event_type"] == "ENCOUNTER"

    def test_filters_by_mmsi(self, _mock_deps):
        """GET /api/gfw/events?mmsi=211234567 returns only events for that vessel."""
        from fastapi.testclient import TestClient

        vessel_events = [e for e in _SAMPLE_EVENTS if e["mmsi"] == 211234567]

        with patch(
            "routes.gfw.list_gfw_events",
            new_callable=AsyncMock,
            return_value=vessel_events,
        ) as mock_list:
            app = api_main.create_app()
            with TestClient(app) as client:
                resp = client.get("/api/gfw/events?mmsi=211234567")

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        for item in body["items"]:
            assert item["mmsi"] == 211234567

        call_kwargs = mock_list.call_args
        assert call_kwargs[1]["mmsi"] == 211234567

    def test_filters_by_time_range(self, _mock_deps):
        """GET /api/gfw/events?start=...&end=... filters by time range."""
        from fastapi.testclient import TestClient

        # Only return events that the repository would return for start_after
        events_after_start = [
            e for e in _SAMPLE_EVENTS
            if e["start_time"] >= datetime(2025, 6, 11, 0, 0, 0, tzinfo=timezone.utc)
        ]

        with patch(
            "routes.gfw.list_gfw_events",
            new_callable=AsyncMock,
            return_value=events_after_start,
        ) as mock_list:
            app = api_main.create_app()
            with TestClient(app) as client:
                resp = client.get(
                    "/api/gfw/events"
                    "?start=2025-06-11T00:00:00Z"
                    "&end=2025-06-13T00:00:00Z"
                )

        assert resp.status_code == 200
        body = resp.json()
        # Only event 2 (June 12) falls within June 11 - June 13 range
        assert body["count"] == 1
        assert body["items"][0]["gfw_event_id"] == "evt-002"

    def test_pagination_params_passed(self, _mock_deps):
        """Custom limit and offset are forwarded to the repository."""
        from fastapi.testclient import TestClient

        with patch(
            "routes.gfw.list_gfw_events",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_list:
            app = api_main.create_app()
            with TestClient(app) as client:
                resp = client.get("/api/gfw/events?limit=25&offset=50")

        assert resp.status_code == 200
        call_kwargs = mock_list.call_args
        assert call_kwargs[1]["limit"] == 25
        assert call_kwargs[1]["offset"] == 50
