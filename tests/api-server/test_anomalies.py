"""Tests for the anomaly REST endpoint (Story 3).

Tests cover:
- GET /api/anomalies returns paginated results
- Severity filter works
- Time range filter works
- Resolved filter works
- Bbox filter works
- Each anomaly includes joined vessel name and tier
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timezone
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
_spec = importlib.util.spec_from_file_location("api_server_main_anomalies", _API_MAIN_PATH)
api_main = importlib.util.module_from_spec(_spec)
sys.modules["api_server_main_anomalies"] = api_main
_spec.loader.exec_module(api_main)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 12, 10, 0, 0, tzinfo=timezone.utc)

_SAMPLE_ANOMALY_ROWS = [
    {
        "id": 1,
        "mmsi": 211234567,
        "rule_id": "ais_gap",
        "severity": "high",
        "points": 30,
        "details": '{"gap_hours": 8}',
        "resolved": False,
        "created_at": _NOW,
        "vessel_name": "NORDIC EXPLORER",
        "risk_tier": "yellow",
    },
    {
        "id": 2,
        "mmsi": 259876543,
        "rule_id": "sts_zone",
        "severity": "critical",
        "points": 50,
        "details": '{"zone": "Laconian Gulf"}',
        "resolved": False,
        "created_at": _NOW,
        "vessel_name": "AEGEAN SPIRIT",
        "risk_tier": "red",
    },
    {
        "id": 3,
        "mmsi": 311222333,
        "rule_id": "speed_anomaly",
        "severity": "moderate",
        "points": 15,
        "details": '{"speed_drop": 4.2}',
        "resolved": True,
        "created_at": _NOW,
        "vessel_name": "BALTIC CARRIER",
        "risk_tier": "green",
    },
]


def _make_mock_session(rows=None, total=None):
    """Create a mock async session that returns configured results.

    The session handles two queries per request:
    1. A COUNT query (returns total)
    2. A SELECT query (returns rows)
    """
    if rows is None:
        rows = []
    if total is None:
        total = len(rows)

    mock_session = AsyncMock()
    call_count = 0

    async def execute_side_effect(stmt, *args, **kwargs):
        nonlocal call_count
        sql = str(stmt.text) if hasattr(stmt, "text") else str(stmt)

        result_mock = MagicMock()

        if "COUNT" in sql:
            result_mock.scalar.return_value = total
        else:
            result_mock.mappings.return_value.all.return_value = rows

        call_count += 1
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
    """Mock database and Redis for anomaly endpoint testing."""
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
    """Patch get_session in the routes.anomalies module."""
    return patch("routes.anomalies.get_session", return_value=mock_factory)


class TestAnomaliesPagination:
    """Test GET /api/anomalies returns paginated results."""

    def test_returns_paginated_response(self, _mock_deps):
        """GET /api/anomalies returns items, total, page, and per_page."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session(rows=_SAMPLE_ANOMALY_ROWS, total=3)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/anomalies")

        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "per_page" in body
        assert body["total"] == 3
        assert body["page"] == 1
        assert len(body["items"]) == 3

    def test_pagination_params_work(self, _mock_deps):
        """Page and per_page query params control pagination."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session(rows=[_SAMPLE_ANOMALY_ROWS[0]], total=3)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/anomalies?page=2&per_page=1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["page"] == 2
        assert body["per_page"] == 1
        assert body["total"] == 3

        # Verify the SQL used correct offset
        calls = mock_session.execute.call_args_list
        # The second call is the data query (first is count)
        data_call_params = calls[1][0][1]  # positional arg [1] = params dict
        assert data_call_params["offset"] == 1  # (page 2 - 1) * per_page 1
        assert data_call_params["limit"] == 1

    def test_empty_result(self, _mock_deps):
        """Returns empty items list when no anomalies match."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session(rows=[], total=0)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/anomalies")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0


class TestAnomaliesSeverityFilter:
    """Test severity filter on GET /api/anomalies."""

    def test_severity_filter_passes_to_query(self, _mock_deps):
        """severity=critical passes the filter to the SQL query."""
        from fastapi.testclient import TestClient

        critical_row = _SAMPLE_ANOMALY_ROWS[1]  # severity=critical
        mock_session = _make_mock_session(rows=[critical_row], total=1)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/anomalies?severity=critical")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["severity"] == "critical"

        # Verify the SQL includes the severity filter
        calls = mock_session.execute.call_args_list
        for call in calls:
            sql = str(call[0][0].text)
            assert "a.severity = :severity" in sql
            assert call[0][1]["severity"] == "critical"


class TestAnomaliesTimeRangeFilter:
    """Test time range filter on GET /api/anomalies."""

    def test_time_range_filter_passes_to_query(self, _mock_deps):
        """start and end params are used in the SQL WHERE clause."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session(rows=[_SAMPLE_ANOMALY_ROWS[0]], total=1)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get(
                    "/api/anomalies"
                    "?start=2026-03-01T00:00:00Z"
                    "&end=2026-03-12T23:59:59Z"
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1

        # Verify both time filters are in the SQL
        calls = mock_session.execute.call_args_list
        for call in calls:
            sql = str(call[0][0].text)
            assert "a.created_at >= :start" in sql
            assert "a.created_at <= :end" in sql


class TestAnomaliesResolvedFilter:
    """Test resolved filter on GET /api/anomalies."""

    def test_resolved_false_filter(self, _mock_deps):
        """resolved=false filters to only unresolved anomalies."""
        from fastapi.testclient import TestClient

        unresolved = [r for r in _SAMPLE_ANOMALY_ROWS if not r["resolved"]]
        mock_session = _make_mock_session(rows=unresolved, total=2)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/anomalies?resolved=false")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        for item in body["items"]:
            assert item["resolved"] is False

        # Verify the SQL has resolved filter
        calls = mock_session.execute.call_args_list
        for call in calls:
            sql = str(call[0][0].text)
            assert "a.resolved = :resolved" in sql
            assert call[0][1]["resolved"] is False


class TestAnomaliesBboxFilter:
    """Test bbox filter on GET /api/anomalies."""

    def test_bbox_filter_passes_to_query(self, _mock_deps):
        """bbox param adds spatial filter using vessel last_lat/last_lon."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session(rows=[_SAMPLE_ANOMALY_ROWS[0]], total=1)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/anomalies?bbox=55.0,5.0,72.0,30.0")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1

        # Verify spatial filter is in the SQL
        calls = mock_session.execute.call_args_list
        for call in calls:
            sql = str(call[0][0].text)
            assert "last_lat" in sql
            assert "last_lon" in sql
            params = call[0][1]
            assert params["sw_lat"] == 55.0
            assert params["sw_lon"] == 5.0
            assert params["ne_lat"] == 72.0
            assert params["ne_lon"] == 30.0

    def test_invalid_bbox_returns_empty(self, _mock_deps):
        """Invalid bbox returns empty result, not a server error."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session()
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/anomalies?bbox=invalid")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0


class TestAnomaliesJoinedVesselData:
    """Test that each anomaly includes vessel_name and risk_tier."""

    def test_anomaly_includes_vessel_name_and_risk_tier(self, _mock_deps):
        """Each returned anomaly has vessel_name and risk_tier from vessel_profiles."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session(rows=_SAMPLE_ANOMALY_ROWS, total=3)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/anomalies")

        assert resp.status_code == 200
        body = resp.json()
        items = body["items"]
        assert len(items) == 3

        # Check first anomaly
        assert items[0]["vessel_name"] == "NORDIC EXPLORER"
        assert items[0]["risk_tier"] == "yellow"

        # Check second anomaly
        assert items[1]["vessel_name"] == "AEGEAN SPIRIT"
        assert items[1]["risk_tier"] == "red"

        # Check third anomaly
        assert items[2]["vessel_name"] == "BALTIC CARRIER"
        assert items[2]["risk_tier"] == "green"

    def test_anomaly_includes_all_event_fields(self, _mock_deps):
        """Each anomaly includes full event data: id, mmsi, rule_id, severity, points, details, resolved, created_at."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session(rows=[_SAMPLE_ANOMALY_ROWS[0]], total=1)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/anomalies")

        assert resp.status_code == 200
        item = resp.json()["items"][0]

        required_fields = {
            "id", "mmsi", "rule_id", "severity", "points",
            "details", "resolved", "created_at",
            "vessel_name", "risk_tier",
        }
        assert required_fields.issubset(item.keys()), (
            f"Missing fields: {required_fields - item.keys()}"
        )

    def test_sql_joins_vessel_profiles(self, _mock_deps):
        """The SQL query joins anomaly_events with vessel_profiles."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session(rows=[], total=0)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                client.get("/api/anomalies")

        # Verify the JOIN is present in both queries
        calls = mock_session.execute.call_args_list
        for call in calls:
            sql = str(call[0][0].text)
            assert "vessel_profiles" in sql
            assert "JOIN" in sql.upper()


class TestAnomaliesCombinedFilters:
    """Test that multiple filters can be combined."""

    def test_severity_and_resolved_combined(self, _mock_deps):
        """severity and resolved filters work together."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session(rows=[_SAMPLE_ANOMALY_ROWS[1]], total=1)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get("/api/anomalies?severity=critical&resolved=false")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1

        # Verify both filters are in the SQL
        calls = mock_session.execute.call_args_list
        for call in calls:
            sql = str(call[0][0].text)
            assert "a.severity = :severity" in sql
            assert "a.resolved = :resolved" in sql
