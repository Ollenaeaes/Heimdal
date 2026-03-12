"""Tests for the enrichment endpoint (Story 5).

Tests cover:
- POST with valid data creates manual_enrichment row and returns 201
- POST with invalid pi_insurer_tier returns 422
- Response includes updated vessel profile with latest enrichment
- POST for nonexistent MMSI returns 404
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import the api-server main module explicitly by file path to avoid
# collision with other services when the full test suite runs.
# ---------------------------------------------------------------------------
_API_SERVER_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "services", "api-server")
)
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

_API_MAIN_PATH = os.path.join(_API_SERVER_DIR, "main.py")
_spec = importlib.util.spec_from_file_location("api_server_main_enrichment", _API_MAIN_PATH)
api_main = importlib.util.module_from_spec(_spec)
sys.modules["api_server_main_enrichment"] = api_main
_spec.loader.exec_module(api_main)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_MMSI = 211234567

_VESSEL_PROFILE = {
    "mmsi": _VALID_MMSI,
    "imo": 9876543,
    "ship_name": "MV Nordic Explorer",
    "ship_type": 70,
    "ship_type_text": "Cargo",
    "flag_country": "DE",
    "call_sign": "DKAB",
    "length": 180.0,
    "width": 28.0,
    "draught": 10.5,
    "destination": "ROTTERDAM",
    "eta": None,
    "last_position_time": None,
    "last_lat": 52.3676,
    "last_lon": 4.9041,
    "risk_score": 35.0,
    "risk_tier": "yellow",
    "sanctions_status": None,
    "pi_tier": None,
    "pi_details": None,
    "owner": "Nordic Shipping GmbH",
    "operator": "Nordic Shipping GmbH",
    "insurer": None,
    "class_society": None,
    "build_year": 2015,
    "dwt": 45000,
    "gross_tonnage": 25000,
    "group_owner": None,
    "registered_owner": "Nordic Shipping GmbH",
    "technical_manager": None,
    "updated_at": None,
}

_ENRICHMENT_ROW = {
    "id": 1,
    "mmsi": _VALID_MMSI,
    "analyst_notes": "Vessel linked to sanctioned entity through subsidiary",
    "source": "Lloyd's Intelligence",
    "pi_tier": "ig_member",
    "confidence": None,
    "attachments": {
        "ownership_chain": ["Alpha Holdings", "Beta Shipping Ltd"],
        "pi_insurer": "Gard P&I",
        "classification_society": "DNV",
        "classification_iacs": True,
        "psc_detentions": 2,
        "psc_deficiencies": 14,
    },
    "created_at": "2026-03-12T10:00:00",
}

_VALID_ENRICHMENT_BODY = {
    "source": "Lloyd's Intelligence",
    "ownership_chain": ["Alpha Holdings", "Beta Shipping Ltd"],
    "pi_insurer": "Gard P&I",
    "pi_insurer_tier": "ig_member",
    "classification_society": "DNV",
    "classification_iacs": True,
    "psc_detentions": 2,
    "psc_deficiencies": 14,
    "notes": "Vessel linked to sanctioned entity through subsidiary",
}


def _make_mock_session(
    vessel_profile: dict | None = _VESSEL_PROFILE,
    enrichment_row: dict | None = _ENRICHMENT_ROW,
    enrichment_id: int = 1,
):
    """Create a mock async session for enrichment tests."""
    mock_session = AsyncMock()

    async def execute_side_effect(stmt, *args, **kwargs):
        sql = str(stmt.text) if hasattr(stmt, "text") else str(stmt)
        result_mock = MagicMock()

        if "vessel_profiles WHERE mmsi" in sql:
            if vessel_profile:
                row_mock = MagicMock()
                row_mock.__iter__ = MagicMock(return_value=iter(vessel_profile.items()))
                row_mock.keys = MagicMock(return_value=vessel_profile.keys())
                row_mock.__getitem__ = lambda self, key: vessel_profile[key]
                result_mock.mappings.return_value.first.return_value = row_mock
            else:
                result_mock.mappings.return_value.first.return_value = None
            return result_mock

        if "INSERT INTO manual_enrichment" in sql:
            row_mock = MagicMock()
            row_mock.__getitem__ = lambda self, idx: enrichment_id
            result_mock.first.return_value = row_mock
            return result_mock

        if "manual_enrichment" in sql and "ORDER BY" in sql:
            if enrichment_row:
                row_mock = MagicMock()
                row_mock.__iter__ = MagicMock(return_value=iter(enrichment_row.items()))
                row_mock.keys = MagicMock(return_value=enrichment_row.keys())
                row_mock.__getitem__ = lambda self, key: enrichment_row[key]
                result_mock.mappings.return_value.first.return_value = row_mock
            else:
                result_mock.mappings.return_value.first.return_value = None
            return result_mock

        # Default
        result_mock.scalar.return_value = 0
        result_mock.mappings.return_value.all.return_value = []
        return result_mock

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)
    mock_session.commit = AsyncMock()
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
    """Mock database and Redis for enrichment endpoint testing."""
    mock_engine = MagicMock()
    mock_engine.url = MagicMock()
    mock_engine.url.database = "test_db"

    mock_redis = AsyncMock()
    mock_redis.close = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.publish = AsyncMock(return_value=1)

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
    """Patch get_session in the enrichment route module and repositories."""
    return patch("routes.enrichment.get_session", return_value=mock_factory)


class TestEnrichmentEndpoint:
    """Test POST /api/vessels/{mmsi}/enrich."""

    def test_post_valid_data_creates_enrichment_row(self, _mock_deps):
        """POST with valid data creates a manual_enrichment row and returns 201."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session()
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/vessels/{_VALID_MMSI}/enrich",
                    json=_VALID_ENRICHMENT_BODY,
                )

        assert resp.status_code == 201

        # Verify the INSERT was called with correct data
        insert_calls = [
            call for call in mock_session.execute.call_args_list
            if "INSERT INTO manual_enrichment" in str(
                call[0][0].text if hasattr(call[0][0], "text") else call[0][0]
            )
        ]
        assert len(insert_calls) == 1
        insert_params = insert_calls[0][0][1]
        assert insert_params["mmsi"] == _VALID_MMSI
        assert insert_params["source"] == "Lloyd's Intelligence"
        assert insert_params["pi_tier"] == "ig_member"
        assert insert_params["analyst_notes"] == "Vessel linked to sanctioned entity through subsidiary"

        # Verify attachments contain the extra fields
        attachments = json.loads(insert_params["attachments"])
        assert attachments["ownership_chain"] == ["Alpha Holdings", "Beta Shipping Ltd"]
        assert attachments["pi_insurer"] == "Gard P&I"
        assert attachments["classification_society"] == "DNV"
        assert attachments["classification_iacs"] is True
        assert attachments["psc_detentions"] == 2
        assert attachments["psc_deficiencies"] == 14

        # Verify commit was called
        mock_session.commit.assert_awaited_once()

    def test_post_invalid_pi_insurer_tier_returns_422(self, _mock_deps):
        """POST with invalid pi_insurer_tier returns 422 validation error."""
        from fastapi.testclient import TestClient

        app = api_main.create_app()
        mock_session = _make_mock_session()
        mock_factory = _FakeSessionFactory(mock_session)

        invalid_body = {
            "source": "Lloyd's Intelligence",
            "pi_insurer_tier": "definitely_not_valid",
            "notes": "Test notes",
        }

        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/vessels/{_VALID_MMSI}/enrich",
                    json=invalid_body,
                )

        assert resp.status_code == 422

    def test_response_includes_updated_vessel_profile(self, _mock_deps):
        """Response includes the updated vessel profile with latest enrichment data."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session()
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/vessels/{_VALID_MMSI}/enrich",
                    json=_VALID_ENRICHMENT_BODY,
                )

        assert resp.status_code == 201
        body = resp.json()

        # Verify vessel profile fields are present
        assert body["mmsi"] == _VALID_MMSI
        assert body["ship_name"] == "MV Nordic Explorer"
        assert body["risk_tier"] == "yellow"
        assert body["flag_country"] == "DE"

        # Verify last_position is included
        assert "last_position" in body
        assert body["last_position"]["lat"] == 52.3676
        assert body["last_position"]["lon"] == 4.9041

        # Verify latest enrichment is included
        assert "latest_enrichment" in body
        assert body["latest_enrichment"]["source"] == "Lloyd's Intelligence"
        assert body["latest_enrichment"]["pi_tier"] == "ig_member"
        assert body["latest_enrichment"]["analyst_notes"] == "Vessel linked to sanctioned entity through subsidiary"

    def test_post_nonexistent_mmsi_returns_404(self, _mock_deps):
        """POST for a nonexistent MMSI returns 404."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session(vessel_profile=None)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/vessels/999999999/enrich",
                    json=_VALID_ENRICHMENT_BODY,
                )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Vessel not found"

    def test_post_publishes_rescoring_event_to_redis(self, _mock_deps):
        """Successful POST publishes re-scoring event to Redis channel."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session()
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/vessels/{_VALID_MMSI}/enrich",
                    json=_VALID_ENRICHMENT_BODY,
                )

        assert resp.status_code == 201
        _mock_deps["redis"].publish.assert_awaited_once_with(
            "heimdal:positions", str(_VALID_MMSI)
        )

    def test_post_missing_source_returns_422(self, _mock_deps):
        """POST without required source field returns 422."""
        from fastapi.testclient import TestClient

        app = api_main.create_app()
        mock_session = _make_mock_session()
        mock_factory = _FakeSessionFactory(mock_session)

        invalid_body = {
            "notes": "Missing the required source field",
        }

        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/vessels/{_VALID_MMSI}/enrich",
                    json=invalid_body,
                )

        assert resp.status_code == 422

    def test_post_minimal_body_succeeds(self, _mock_deps):
        """POST with only required fields (source) succeeds."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session()
        mock_factory = _FakeSessionFactory(mock_session)

        minimal_body = {"source": "Manual analyst entry"}

        app = api_main.create_app()
        with _patch_get_session(mock_factory):
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/vessels/{_VALID_MMSI}/enrich",
                    json=minimal_body,
                )

        assert resp.status_code == 201

        # Verify attachments is empty when no extra fields provided
        insert_calls = [
            call for call in mock_session.execute.call_args_list
            if "INSERT INTO manual_enrichment" in str(
                call[0][0].text if hasattr(call[0][0], "text") else call[0][0]
            )
        ]
        assert len(insert_calls) == 1
        insert_params = insert_calls[0][0][1]
        assert insert_params["source"] == "Manual analyst entry"
        assert insert_params["analyst_notes"] is None
        assert insert_params["pi_tier"] is None
        assert json.loads(insert_params["attachments"]) == {}
