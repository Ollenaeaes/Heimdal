"""Tests for equasis data in the vessel detail endpoint (Story 7).

Tests cover:
- Vessel detail includes equasis.latest with all sections when data exists
- Vessel detail has equasis=null when no data
- equasis.upload_count matches actual upload count
- equasis.uploads contains the list of uploads with id, upload_timestamp, edition_date
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
_spec = importlib.util.spec_from_file_location("api_server_main_equasis_detail", _API_MAIN_PATH)
api_main = importlib.util.module_from_spec(_spec)
sys.modules["api_server_main_equasis_detail"] = api_main
_spec.loader.exec_module(api_main)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_vessel_row(mmsi: int, **extra) -> dict:
    """Create a vessel profile row dict with sensible defaults."""
    defaults = {
        "mmsi": mmsi,
        "imo": 9000001,
        "ship_name": "Test Vessel",
        "ship_type": 70,
        "ship_type_text": "Cargo",
        "flag_country": "NOR",
        "call_sign": "ABCD",
        "length": 200,
        "width": 30,
        "draught": 12.5,
        "destination": "OSLO",
        "eta": None,
        "last_position_time": datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        "last_lat": 59.91,
        "last_lon": 10.75,
        "risk_score": 10.0,
        "risk_tier": "green",
        "sanctions_status": None,
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
    }
    defaults.update(extra)
    return defaults


def _make_equasis_row(
    row_id: int,
    mmsi: int,
    upload_timestamp: datetime | None = None,
    edition_date: str = "2025-01-15",
) -> dict:
    """Create an equasis_data row dict."""
    if upload_timestamp is None:
        upload_timestamp = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    return {
        "id": row_id,
        "mmsi": mmsi,
        "imo": 9000001,
        "upload_timestamp": upload_timestamp,
        "edition_date": edition_date,
        "vessel_name": "Test Vessel",
        "flag": "Norway",
        "classification_society": "DNV",
        "inspections": [{"type": "PSC", "date": "2025-01-10", "result": "No deficiencies"}],
        "detentions": [],
        "company": {"name": "Acme Shipping", "imo": "1234567"},
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
# Tests: Equasis data in GET /api/vessels/{mmsi}
# ---------------------------------------------------------------------------


class TestEquasisVesselDetail:
    """Test equasis data inclusion in GET /api/vessels/{mmsi}."""

    def test_includes_equasis_latest_when_data_exists(self, _mock_deps):
        """Vessel detail includes equasis.latest with all sections when data exists."""
        from fastapi.testclient import TestClient

        mmsi = 211000100
        vessel = _make_vessel_row(mmsi)
        equasis_row = _make_equasis_row(1, mmsi)

        # The get_vessel endpoint issues queries matching these SQL substrings.
        # We need equasis_data queries to return data while other queries return defaults.
        # The mock matches substrings in order, so we use specific keys.
        mock_session = _make_mock_session({
            "vessel_profiles": [vessel],
            "anomaly_events": [],
            "manual_enrichment": [],
            "vessel_positions": [],
            "equasis_data": [equasis_row],
            "COUNT": 1,
        })
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get(f"/api/vessels/{mmsi}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["equasis"] is not None
        latest = body["equasis"]["latest"]
        assert latest is not None
        assert latest["mmsi"] == mmsi
        assert latest["vessel_name"] == "Test Vessel"
        assert latest["flag"] == "Norway"
        assert latest["classification_society"] == "DNV"
        assert latest["inspections"] is not None
        assert latest["company"] is not None

    def test_equasis_null_when_no_data(self, _mock_deps):
        """Vessel detail has equasis=null when no equasis data exists."""
        from fastapi.testclient import TestClient

        mmsi = 211000101
        vessel = _make_vessel_row(mmsi)

        mock_session = _make_mock_session({
            "vessel_profiles": [vessel],
            "anomaly_events": [],
            "manual_enrichment": [],
            "vessel_positions": [],
            # No equasis_data key — defaults will return empty/None
        })
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get(f"/api/vessels/{mmsi}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["equasis"] is None

    def test_equasis_upload_count_matches(self, _mock_deps):
        """equasis.upload_count matches the actual number of uploads."""
        from fastapi.testclient import TestClient

        mmsi = 211000102
        vessel = _make_vessel_row(mmsi)

        t1 = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2025, 5, 15, 10, 0, 0, tzinfo=timezone.utc)
        t3 = datetime(2025, 4, 20, 10, 0, 0, tzinfo=timezone.utc)

        equasis_rows = [
            _make_equasis_row(1, mmsi, upload_timestamp=t1, edition_date="2025-06-01"),
            _make_equasis_row(2, mmsi, upload_timestamp=t2, edition_date="2025-05-15"),
            _make_equasis_row(3, mmsi, upload_timestamp=t3, edition_date="2025-04-20"),
        ]

        # We need a custom mock session because the default substring matching
        # can't distinguish the three equasis_data queries (SELECT *, COUNT, SELECT id).
        # Build a mock that checks query patterns more precisely.
        mock_session = AsyncMock()
        call_count = {"equasis": 0}

        async def execute_side_effect(stmt, params=None, *args, **kwargs):
            sql = str(stmt.text) if hasattr(stmt, "text") else str(stmt)
            result_mock = MagicMock()

            if "vessel_profiles" in sql:
                result_mock.mappings.return_value.first.return_value = vessel
                return result_mock
            if "anomaly_events" in sql:
                result_mock.mappings.return_value.all.return_value = []
                return result_mock
            if "manual_enrichment" in sql:
                result_mock.mappings.return_value.first.return_value = None
                return result_mock
            if "vessel_positions" in sql:
                result_mock.mappings.return_value.first.return_value = None
                return result_mock
            if "COUNT" in sql and "equasis_data" in sql:
                result_mock.scalar.return_value = 3
                return result_mock
            if "SELECT *" in sql and "equasis_data" in sql:
                result_mock.mappings.return_value.first.return_value = equasis_rows[0]
                return result_mock
            if "equasis_data" in sql:
                result_mock.mappings.return_value.all.return_value = equasis_rows
                return result_mock

            # Default
            result_mock.scalar.return_value = 0
            result_mock.mappings.return_value.all.return_value = []
            result_mock.mappings.return_value.first.return_value = None
            return result_mock

        mock_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get(f"/api/vessels/{mmsi}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["equasis"] is not None
        assert body["equasis"]["upload_count"] == 3

    def test_equasis_uploads_list(self, _mock_deps):
        """equasis.uploads contains list of uploads with id, upload_timestamp, edition_date."""
        from fastapi.testclient import TestClient

        mmsi = 211000103
        vessel = _make_vessel_row(mmsi)

        t1 = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2025, 5, 15, 10, 0, 0, tzinfo=timezone.utc)

        equasis_rows = [
            _make_equasis_row(1, mmsi, upload_timestamp=t1, edition_date="2025-06-01"),
            _make_equasis_row(2, mmsi, upload_timestamp=t2, edition_date="2025-05-15"),
        ]

        mock_session = _make_mock_session({
            "vessel_profiles": [vessel],
            "anomaly_events": [],
            "manual_enrichment": [],
            "vessel_positions": [],
            "equasis_data": equasis_rows,
            "COUNT": 2,
        })
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.get(f"/api/vessels/{mmsi}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["equasis"] is not None

        uploads = body["equasis"]["uploads"]
        assert len(uploads) == 2

        # Each upload should have id, upload_timestamp, edition_date
        for upload in uploads:
            assert "id" in upload
            assert "upload_timestamp" in upload
            assert "edition_date" in upload

        # Verify correct data
        assert uploads[0]["id"] == 1
        assert uploads[0]["edition_date"] == "2025-06-01"
        assert uploads[1]["id"] == 2
        assert uploads[1]["edition_date"] == "2025-05-15"
