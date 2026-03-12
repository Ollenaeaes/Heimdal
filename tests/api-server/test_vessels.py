"""Tests for the vessel REST endpoints (Story 2).

Tests cover:
- GET /api/vessels returns paginated results with total count
- Risk tier filter returns only matching vessels
- Bbox filter works with spatial query on last_lat/last_lon
- Ship type filter works with comma-separated codes
- Sanctions hit filter returns only vessels with non-empty sanctions_status
- Active since filter returns only recently active vessels
- GET /api/vessels/{mmsi} returns full profile for existing vessel
- GET /api/vessels/{mmsi} returns 404 for nonexistent vessel
- GET /api/vessels/{mmsi}/track returns chronologically ordered positions
- Track simplification reduces point count compared to full resolution
- Pagination params (page, per_page) work correctly
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
_spec = importlib.util.spec_from_file_location("api_server_main_vessels", _API_MAIN_PATH)
api_main = importlib.util.module_from_spec(_spec)
sys.modules["api_server_main_vessels"] = api_main
_spec.loader.exec_module(api_main)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_vessel_row(
    mmsi: int,
    *,
    ship_name: str = "Test Vessel",
    risk_tier: str = "green",
    risk_score: float = 10.0,
    ship_type: int = 70,
    flag_country: str = "NOR",
    imo: int | None = 9000001,
    last_lat: float = 59.91,
    last_lon: float = 10.75,
    last_position_time: datetime | None = None,
    sanctions_status: str | None = None,
    **extra,
) -> dict:
    """Create a vessel profile row dict."""
    if last_position_time is None:
        last_position_time = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    return {
        "mmsi": mmsi,
        "imo": imo,
        "ship_name": ship_name,
        "ship_type": ship_type,
        "ship_type_text": "Cargo",
        "flag_country": flag_country,
        "call_sign": "ABCD",
        "length": 200,
        "width": 30,
        "draught": 12.5,
        "destination": "OSLO",
        "eta": None,
        "last_position_time": last_position_time,
        "last_lat": last_lat,
        "last_lon": last_lon,
        "risk_score": risk_score,
        "risk_tier": risk_tier,
        "sanctions_status": sanctions_status,
        "pi_tier": None,
        "pi_details": None,
        "owner": "Acme Shipping",
        "operator": "Acme Ops",
        "insurer": None,
        "class_society": "DNV",
        "build_year": 2015,
        "dwt": 50000,
        "gross_tonnage": 30000,
        "group_owner": None,
        "registered_owner": "Acme Shipping AS",
        "technical_manager": None,
        "updated_at": datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        **extra,
    }


def _make_position_row(
    timestamp: datetime,
    lat: float = 59.91,
    lon: float = 10.75,
    sog: float = 12.5,
    cog: float = 180.0,
    draught: float = 10.0,
) -> dict:
    """Create a vessel position row dict."""
    return {
        "timestamp": timestamp,
        "lat": lat,
        "lon": lon,
        "sog": sog,
        "cog": cog,
        "draught": draught,
    }


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


def _make_mock_session(query_results: dict | None = None):
    """Create a mock async session with configurable query results.

    query_results maps SQL substrings to result values:
      {"COUNT": scalar_value, "vessel_profiles": [row_dicts], ...}
    """
    if query_results is None:
        query_results = {}

    mock_session = AsyncMock()

    async def execute_side_effect(stmt, params=None, *args, **kwargs):
        sql = str(stmt.text) if hasattr(stmt, "text") else str(stmt)
        result_mock = MagicMock()

        for key, value in query_results.items():
            if key in sql:
                if isinstance(value, list):
                    result_mock.mappings.return_value.all.return_value = value
                    result_mock.mappings.return_value.first.return_value = (
                        value[0] if value else None
                    )
                elif isinstance(value, Exception):
                    raise value
                else:
                    result_mock.scalar.return_value = value
                return result_mock

        # Default
        result_mock.scalar.return_value = 0
        result_mock.mappings.return_value.all.return_value = []
        result_mock.mappings.return_value.first.return_value = None
        return result_mock

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)
    return mock_session


@pytest.fixture()
def _mock_deps():
    """Mock database and Redis for vessel endpoint testing."""
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
    """Patch get_session in the routes.vessels module."""
    return patch("routes.vessels.get_session", return_value=mock_factory)


# ---------------------------------------------------------------------------
# Tests: GET /api/vessels
# ---------------------------------------------------------------------------


class TestListVessels:
    """Test GET /api/vessels."""

    def test_returns_paginated_results_with_total(self, _mock_deps):
        """GET /api/vessels returns paginated results with items, total, page, per_page."""
        from fastapi.testclient import TestClient

        vessels = [
            _make_vessel_row(211000001, ship_name="Nordic Star", risk_score=85.0),
            _make_vessel_row(211000002, ship_name="Baltic Trader", risk_score=42.0),
        ]

        # The list endpoint issues two queries: COUNT(*) then SELECT
        # COUNT query contains "COUNT", SELECT query contains the summary fields
        mock_session = _make_mock_session({
            "COUNT": 2,
            "mmsi": vessels,
        })
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/vessels")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["page"] == 1
        assert body["per_page"] == 100
        assert len(body["items"]) == 2

        # Verify summary fields present
        item = body["items"][0]
        assert "mmsi" in item
        assert "imo" in item
        assert "ship_name" in item
        assert "flag_state" in item
        assert "ship_type" in item
        assert "risk_tier" in item
        assert "risk_score" in item
        assert "last_position" in item
        pos = item["last_position"]
        assert "lat" in pos
        assert "lon" in pos
        assert "sog" in pos
        assert "cog" in pos
        assert "timestamp" in pos

    def test_risk_tier_filter(self, _mock_deps):
        """GET /api/vessels?risk_tier=red returns only red-tier vessels."""
        from fastapi.testclient import TestClient

        red_vessels = [
            _make_vessel_row(211000003, ship_name="Crimson Voyager", risk_tier="red", risk_score=92.0),
        ]
        mock_session = _make_mock_session({"COUNT": 1, "mmsi": red_vessels})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/vessels?risk_tier=red")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["risk_tier"] == "red"

        # Verify the SQL included the risk_tier filter
        calls = mock_session.execute.call_args_list
        # Both queries (COUNT and SELECT) should have risk_tier in params
        for call in calls:
            sql = str(call[0][0].text) if hasattr(call[0][0], "text") else str(call[0][0])
            if "risk_tier" in sql:
                assert "risk_tier" in call[0][1] or "risk_tier" in (call[1] if len(call) > 1 else {})

    def test_bbox_filter(self, _mock_deps):
        """GET /api/vessels?bbox=59.0,10.0,60.0,11.0 filters by bounding box."""
        from fastapi.testclient import TestClient

        vessels_in_bbox = [
            _make_vessel_row(211000004, ship_name="Fjord Explorer", last_lat=59.5, last_lon=10.5),
        ]
        mock_session = _make_mock_session({"COUNT": 1, "mmsi": vessels_in_bbox})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/vessels?bbox=59.0,10.0,60.0,11.0")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1

        # Verify bbox params were passed to SQL
        calls = mock_session.execute.call_args_list
        count_sql = str(calls[0][0][0].text)
        assert "last_lat" in count_sql
        assert "last_lon" in count_sql

    def test_bbox_invalid_format(self, _mock_deps):
        """GET /api/vessels?bbox=invalid returns 400."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session({})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/vessels?bbox=59.0,10.0")

        assert resp.status_code == 400

    def test_ship_type_filter(self, _mock_deps):
        """GET /api/vessels?ship_type=80,81,82 filters by ship type codes."""
        from fastapi.testclient import TestClient

        tankers = [
            _make_vessel_row(211000005, ship_name="Crude Carrier", ship_type=80),
        ]
        mock_session = _make_mock_session({"COUNT": 1, "mmsi": tankers})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/vessels?ship_type=80,81,82")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1

        # Verify ship_types param was included
        calls = mock_session.execute.call_args_list
        count_params = calls[0][0][1]
        assert count_params["ship_types"] == [80, 81, 82]

    def test_sanctions_hit_filter(self, _mock_deps):
        """GET /api/vessels?sanctions_hit=true returns only sanctioned vessels."""
        from fastapi.testclient import TestClient

        sanctioned = [
            _make_vessel_row(
                211000006,
                ship_name="Shadow Tanker",
                sanctions_status="OFAC listed",
                risk_tier="red",
                risk_score=99.0,
            ),
        ]
        mock_session = _make_mock_session({"COUNT": 1, "mmsi": sanctioned})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/vessels?sanctions_hit=true")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1

        # Verify sanctions filter in SQL
        calls = mock_session.execute.call_args_list
        count_sql = str(calls[0][0][0].text)
        assert "sanctions_status" in count_sql

    def test_active_since_filter(self, _mock_deps):
        """GET /api/vessels?active_since=<datetime> filters by last position time."""
        from fastapi.testclient import TestClient

        recent = [
            _make_vessel_row(
                211000007,
                ship_name="Fresh Signal",
                last_position_time=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
        ]
        mock_session = _make_mock_session({"COUNT": 1, "mmsi": recent})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/vessels?active_since=2025-06-01T00:00:00Z")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1

        # Verify active_since param
        calls = mock_session.execute.call_args_list
        count_sql = str(calls[0][0][0].text)
        assert "last_position_time" in count_sql

    def test_pagination_page_2(self, _mock_deps):
        """GET /api/vessels?page=2&per_page=1 returns correct page."""
        from fastapi.testclient import TestClient

        vessel_page2 = [
            _make_vessel_row(211000009, ship_name="Page Two Vessel"),
        ]
        mock_session = _make_mock_session({"COUNT": 3, "mmsi": vessel_page2})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/vessels?page=2&per_page=1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert body["page"] == 2
        assert body["per_page"] == 1
        assert len(body["items"]) == 1

        # Verify offset = (page-1) * per_page = 1
        calls = mock_session.execute.call_args_list
        select_params = calls[1][0][1]
        assert select_params["offset"] == 1
        assert select_params["limit"] == 1

    def test_empty_list(self, _mock_deps):
        """GET /api/vessels returns empty items when no vessels exist."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session({"COUNT": 0, "mmsi": []})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/vessels")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []


# ---------------------------------------------------------------------------
# Tests: GET /api/vessels/{mmsi}
# ---------------------------------------------------------------------------


class TestGetVessel:
    """Test GET /api/vessels/{mmsi}."""

    def test_returns_full_profile_for_existing_vessel(self, _mock_deps):
        """GET /api/vessels/{mmsi} returns full vessel profile with enrichments."""
        from fastapi.testclient import TestClient

        vessel = _make_vessel_row(
            211000010,
            ship_name="Detailed Vessel",
            risk_tier="yellow",
            risk_score=55.0,
            sanctions_status="Under review",
        )
        enrichment = {
            "id": 1,
            "mmsi": 211000010,
            "analyst_notes": "Flagged for suspicious port calls",
            "source": "analyst",
            "pi_tier": "high",
            "confidence": 0.85,
            "attachments": None,
            "created_at": datetime(2025, 5, 30, 10, 0, 0, tzinfo=timezone.utc),
        }

        mock_session = _make_mock_session({
            "vessel_profiles": [vessel],
            "anomaly_events": 3,
            "manual_enrichment": [enrichment],
        })
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/vessels/211000010")

        assert resp.status_code == 200
        body = resp.json()
        assert body["mmsi"] == 211000010
        assert body["ship_name"] == "Detailed Vessel"
        assert body["risk_tier"] == "yellow"
        assert body["sanctions_status"] == "Under review"
        assert body["active_anomaly_count"] == 3
        assert body["latest_enrichment"] is not None
        assert body["latest_enrichment"]["analyst_notes"] == "Flagged for suspicious port calls"

        # Verify last_position is included
        assert "last_position" in body
        assert body["last_position"]["lat"] == vessel["last_lat"]
        assert body["last_position"]["lon"] == vessel["last_lon"]

    def test_returns_404_for_nonexistent_vessel(self, _mock_deps):
        """GET /api/vessels/{mmsi} returns 404 when vessel does not exist."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session({})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/vessels/999999999")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_profile_with_no_enrichment(self, _mock_deps):
        """GET /api/vessels/{mmsi} returns null latest_enrichment when none exist."""
        from fastapi.testclient import TestClient

        vessel = _make_vessel_row(211000011, ship_name="Clean Vessel")

        mock_session = _make_mock_session({
            "vessel_profiles": [vessel],
            "anomaly_events": 0,
        })
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/vessels/211000011")

        assert resp.status_code == 200
        body = resp.json()
        assert body["latest_enrichment"] is None
        assert body["active_anomaly_count"] == 0


# ---------------------------------------------------------------------------
# Tests: GET /api/vessels/{mmsi}/track
# ---------------------------------------------------------------------------


class TestGetVesselTrack:
    """Test GET /api/vessels/{mmsi}/track."""

    def test_returns_chronologically_ordered_positions(self, _mock_deps):
        """GET /api/vessels/{mmsi}/track returns positions in chronological order."""
        from fastapi.testclient import TestClient

        t1 = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2025, 6, 1, 10, 30, 0, tzinfo=timezone.utc)
        t3 = datetime(2025, 6, 1, 11, 0, 0, tzinfo=timezone.utc)

        positions = [
            _make_position_row(t1, lat=59.90, lon=10.70, sog=10.0, cog=90.0),
            _make_position_row(t2, lat=59.91, lon=10.75, sog=11.0, cog=95.0),
            _make_position_row(t3, lat=59.92, lon=10.80, sog=12.0, cog=100.0),
        ]

        mock_session = _make_mock_session({"vessel_positions": positions})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get(
                    "/api/vessels/211000012/track"
                    "?start=2025-06-01T09:00:00Z&end=2025-06-01T12:00:00Z"
                )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 3

        # Verify chronological order and fields
        assert body[0]["lat"] == 59.90
        assert body[1]["lat"] == 59.91
        assert body[2]["lat"] == 59.92
        assert "sog" in body[0]
        assert "cog" in body[0]
        assert "draught" in body[0]
        assert "timestamp" in body[0]

    def test_track_with_default_time_range(self, _mock_deps):
        """GET /api/vessels/{mmsi}/track uses last 24h as default time range."""
        from fastapi.testclient import TestClient

        positions = [
            _make_position_row(
                datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
        ]

        mock_session = _make_mock_session({"vessel_positions": positions})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/vessels/211000013/track")

        assert resp.status_code == 200
        # Verify query was executed with start/end time params
        calls = mock_session.execute.call_args_list
        params = calls[0][0][1]
        assert "start_time" in params
        assert "end_time" in params
        # Default is 24h window
        delta = params["end_time"] - params["start_time"]
        assert abs(delta.total_seconds() - 86400) < 5  # within 5 seconds of 24h

    def test_track_simplification_uses_st_simplify(self, _mock_deps):
        """GET /api/vessels/{mmsi}/track?simplify=0.001 includes ST_Simplify in SQL."""
        from fastapi.testclient import TestClient

        # Return fewer points to simulate simplification
        simplified_positions = [
            _make_position_row(
                datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
                lat=59.90,
                lon=10.70,
            ),
            _make_position_row(
                datetime(2025, 6, 1, 11, 0, 0, tzinfo=timezone.utc),
                lat=59.92,
                lon=10.80,
            ),
        ]

        mock_session = _make_mock_session({"vessel_positions": simplified_positions})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get(
                    "/api/vessels/211000014/track"
                    "?simplify=0.001"
                    "&start=2025-06-01T09:00:00Z&end=2025-06-01T12:00:00Z"
                )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2

        # Verify ST_Simplify was in the SQL
        calls = mock_session.execute.call_args_list
        sql = str(calls[0][0][0].text)
        assert "ST_Simplify" in sql
        params = calls[0][0][1]
        assert params["tolerance"] == 0.001

    def test_track_without_simplify_no_st_simplify(self, _mock_deps):
        """GET /api/vessels/{mmsi}/track without simplify does NOT use ST_Simplify."""
        from fastapi.testclient import TestClient

        positions = [
            _make_position_row(datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)),
        ]

        mock_session = _make_mock_session({"vessel_positions": positions})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get(
                    "/api/vessels/211000015/track"
                    "?start=2025-06-01T09:00:00Z&end=2025-06-01T12:00:00Z"
                )

        assert resp.status_code == 200

        calls = mock_session.execute.call_args_list
        sql = str(calls[0][0][0].text)
        assert "ST_Simplify" not in sql

    def test_track_empty_result(self, _mock_deps):
        """GET /api/vessels/{mmsi}/track returns empty array when no positions found."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session({"vessel_positions": []})
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/vessels/211000016/track")

        assert resp.status_code == 200
        assert resp.json() == []
