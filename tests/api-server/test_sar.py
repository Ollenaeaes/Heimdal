"""Tests for SAR detection endpoints (Story 4).

Tests cover:
- GET /api/sar/detections returns paginated results
- GET /api/sar/detections filters by is_dark
- GET /api/sar/detections filters by bbox (spatial filter)
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
_spec = importlib.util.spec_from_file_location("api_server_main_sar", _API_MAIN_PATH)
api_main = importlib.util.module_from_spec(_spec)
sys.modules["api_server_main_sar"] = api_main
_spec.loader.exec_module(api_main)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_SAMPLE_DETECTIONS = [
    {
        "id": 1,
        "detection_time": datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone.utc),
        "lat": 25.5,
        "lon": 55.3,
        "length_m": 120.0,
        "width_m": 20.0,
        "heading_deg": 180.0,
        "confidence": 0.92,
        "is_dark": True,
        "matched_mmsi": None,
        "match_distance_m": None,
        "source": "gfw",
        "gfw_detection_id": "det-001",
        "matching_score": None,
        "fishing_score": 0.1,
        "created_at": datetime(2025, 6, 15, 11, 0, 0, tzinfo=timezone.utc),
    },
    {
        "id": 2,
        "detection_time": datetime(2025, 6, 15, 11, 0, 0, tzinfo=timezone.utc),
        "lat": 26.0,
        "lon": 56.0,
        "length_m": 80.0,
        "width_m": 12.0,
        "heading_deg": 90.0,
        "confidence": 0.85,
        "is_dark": False,
        "matched_mmsi": 211234567,
        "match_distance_m": 150.0,
        "source": "gfw",
        "gfw_detection_id": "det-002",
        "matching_score": 0.88,
        "fishing_score": 0.3,
        "created_at": datetime(2025, 6, 15, 11, 30, 0, tzinfo=timezone.utc),
    },
    {
        "id": 3,
        "detection_time": datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        "lat": 60.0,
        "lon": 10.0,
        "length_m": 200.0,
        "width_m": 30.0,
        "heading_deg": 270.0,
        "confidence": 0.95,
        "is_dark": True,
        "matched_mmsi": None,
        "match_distance_m": None,
        "source": "sentinel",
        "gfw_detection_id": "det-003",
        "matching_score": None,
        "fishing_score": None,
        "created_at": datetime(2025, 6, 15, 12, 30, 0, tzinfo=timezone.utc),
    },
]


@pytest.fixture()
def _mock_deps():
    """Mock database and Redis for SAR endpoint testing."""
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


class TestSarDetections:
    """Test GET /api/sar/detections."""

    def test_returns_paginated_results(self, _mock_deps):
        """GET /api/sar/detections returns items with count, limit, offset."""
        from fastapi.testclient import TestClient

        with patch(
            "routes.sar.list_sar_detections",
            new_callable=AsyncMock,
            return_value=_SAMPLE_DETECTIONS,
        ):
            app = api_main.create_app()
            with TestClient(app) as client:
                resp = client.get("/api/sar/detections")

        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert body["total"] == 3
        assert body["page"] == 1
        assert body["per_page"] == 100
        assert len(body["items"]) == 3

    def test_filters_by_is_dark_true(self, _mock_deps):
        """GET /api/sar/detections?is_dark=true returns only dark detections."""
        from fastapi.testclient import TestClient

        dark_only = [d for d in _SAMPLE_DETECTIONS if d["is_dark"]]

        with patch(
            "routes.sar.list_sar_detections",
            new_callable=AsyncMock,
            return_value=dark_only,
        ) as mock_list:
            app = api_main.create_app()
            with TestClient(app) as client:
                resp = client.get("/api/sar/detections?is_dark=true")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        # Verify all returned items are dark
        for item in body["items"]:
            assert item["is_dark"] is True

        # Verify the repository was called with is_dark=True
        call_kwargs = mock_list.call_args
        assert call_kwargs[1]["is_dark"] is True

    def test_filters_by_is_dark_false(self, _mock_deps):
        """GET /api/sar/detections?is_dark=false returns only matched detections."""
        from fastapi.testclient import TestClient

        matched_only = [d for d in _SAMPLE_DETECTIONS if not d["is_dark"]]

        with patch(
            "routes.sar.list_sar_detections",
            new_callable=AsyncMock,
            return_value=matched_only,
        ) as mock_list:
            app = api_main.create_app()
            with TestClient(app) as client:
                resp = client.get("/api/sar/detections?is_dark=false")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["is_dark"] is False
        call_kwargs = mock_list.call_args
        assert call_kwargs[1]["is_dark"] is False

    def test_filters_by_bbox(self, _mock_deps):
        """GET /api/sar/detections?bbox=54,25,57,27 applies spatial filter."""
        from fastapi.testclient import TestClient

        with patch(
            "routes.sar.list_sar_detections",
            new_callable=AsyncMock,
            return_value=_SAMPLE_DETECTIONS,
        ):
            app = api_main.create_app()
            with TestClient(app) as client:
                # bbox sw_lat=25,sw_lon=54,ne_lat=27,ne_lon=57 covers the Gulf area
                resp = client.get("/api/sar/detections?bbox=25,54,27,57")

        assert resp.status_code == 200
        body = resp.json()
        # Only detections at lat=25.5,lon=55.3 and lat=26.0,lon=56.0 should match
        assert body["total"] == 2
        lats = {item["lat"] for item in body["items"]}
        assert 25.5 in lats
        assert 26.0 in lats
        assert 60.0 not in lats

    def test_bbox_excludes_all(self, _mock_deps):
        """bbox that matches no detections returns empty list."""
        from fastapi.testclient import TestClient

        with patch(
            "routes.sar.list_sar_detections",
            new_callable=AsyncMock,
            return_value=_SAMPLE_DETECTIONS,
        ):
            app = api_main.create_app()
            with TestClient(app) as client:
                resp = client.get("/api/sar/detections?bbox=0,0,1,1")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_pagination_params_passed(self, _mock_deps):
        """Page and per_page are converted to limit/offset for the repository."""
        from fastapi.testclient import TestClient

        with patch(
            "routes.sar.list_sar_detections",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_list:
            app = api_main.create_app()
            with TestClient(app) as client:
                resp = client.get("/api/sar/detections?page=3&per_page=10")

        assert resp.status_code == 200
        call_kwargs = mock_list.call_args
        assert call_kwargs[1]["limit"] == 10
        assert call_kwargs[1]["offset"] == 20
