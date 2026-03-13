"""Tests for the Equasis upload endpoint (Story 3).

Tests cover:
- Upload valid PDF with matching mmsi → 201
- Upload with mmsi mismatch → 422
- Upload without mmsi, existing vessel → enriches that vessel
- Upload without mmsi, new vessel → creates vessel + equasis_data, response has created: true
- Upload non-PDF → 400
- Upload non-Equasis PDF → 422
- vessel_profiles fields updated correctly
- Re-scoring event published to Redis
- Second upload creates new equasis_data row
- GET /api/equasis/{mmsi}/history
- GET /api/equasis/{mmsi}/upload/{upload_id}
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
_spec = importlib.util.spec_from_file_location("api_server_main_equasis_upload", _API_MAIN_PATH)
api_main = importlib.util.module_from_spec(_spec)
sys.modules["api_server_main_equasis_upload"] = api_main
_spec.loader.exec_module(api_main)


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_VALID_MMSI = 613414602
_VALID_IMO = 9236353

_PARSED_PDF = {
    "ship_particulars": {
        "imo": _VALID_IMO,
        "name": "BLUE",
        "call_sign": "D5FQ7",
        "mmsi": _VALID_MMSI,
        "gross_tonnage": 25000,
        "dwt": 45000,
        "ship_type": "Bulk Carrier",
        "build_year": 2001,
        "flag": "Liberia",
        "status": "In Service/Commission",
        "last_update": "01/03/2026",
    },
    "management": [
        {
            "company_imo": 1234567,
            "role": "Registered owner",
            "company_name": "BLUE SHIPPING LTD",
            "address": None,
            "date_of_effect": "since 01/01/2020",
        },
        {
            "company_imo": 2345678,
            "role": "ISM Manager",
            "company_name": "MARITIME MANAGEMENT CO",
            "address": None,
            "date_of_effect": "since 15/06/2019",
        },
        {
            "company_imo": 3456789,
            "role": "Ship manager/ Commercial manager",
            "company_name": "GLOBAL SHIP MANAGERS",
            "address": None,
            "date_of_effect": "since 01/03/2021",
        },
    ],
    "classification_status": [
        {
            "society": "Lloyd's Register",
            "date_change": "since 15/01/2020",
            "status": "Delivered",
            "reason": None,
        },
        {
            "society": "Bureau Veritas",
            "date_change": "during 2015",
            "status": "Withdrawn",
            "reason": "by society for other reasons",
        },
    ],
    "classification_surveys": [],
    "safety_certificates": [],
    "psc_inspections": [
        {"authority": "France", "port": "Marseille", "date": "15/02/2025", "detention": False,
         "psc_organisation": "Paris MoU", "inspection_type": "Initial inspection",
         "duration_days": 1, "deficiencies": 3},
    ] * 32,  # 32 PSC inspections
    "human_element_deficiencies": [],
    "name_history": [
        {"name": "BLUE", "date_of_effect": "since 01/02/2024", "source": "IHS Maritime"},
        {"name": "Julia A", "date_of_effect": "since 01/09/2022", "source": "IHS Maritime"},
        {"name": "Sea Diamond", "date_of_effect": "since 01/06/2020", "source": "IHS Maritime"},
        {"name": "Star Nova", "date_of_effect": "since 15/03/2018", "source": "IHS Maritime"},
        {"name": "Ocean Pearl", "date_of_effect": "since 01/01/2016", "source": "IHS Maritime"},
        {"name": "Bright Sky", "date_of_effect": "since 10/07/2012", "source": "IHS Maritime"},
        {"name": "Pacific Wave", "date_of_effect": "since 01/01/2005", "source": "IHS Maritime"},
    ],
    "flag_history": [
        {"flag": "Liberia", "date_of_effect": "since 01/02/2024", "source": "IHS Maritime"},
    ] * 14,  # 14 flag changes
    "company_history": [
        {"company": "BLUE SHIPPING LTD", "role": "Registered owner",
         "date_of_effect": "since 01/01/2020", "sources": "IHS Maritime"},
    ] * 17,  # 17 companies
    "edition_date": "13/03/2026",
}

_VESSEL_PROFILE = {
    "mmsi": _VALID_MMSI,
    "imo": _VALID_IMO,
    "ship_name": "BLUE",
    "ship_type": 70,
    "ship_type_text": "Bulk Carrier",
    "flag_country": "Liberia",
    "call_sign": "D5FQ7",
    "length": 180.0,
    "width": 28.0,
    "draught": 10.5,
    "destination": None,
    "eta": None,
    "last_position_time": None,
    "last_lat": None,
    "last_lon": None,
    "risk_score": 45.0,
    "risk_tier": "yellow",
    "sanctions_status": None,
    "pi_tier": None,
    "pi_details": None,
    "owner": None,
    "operator": None,
    "insurer": None,
    "class_society": None,
    "build_year": 2001,
    "dwt": 45000,
    "gross_tonnage": 25000,
    "group_owner": None,
    "registered_owner": None,
    "technical_manager": None,
    "updated_at": None,
}


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


@pytest.fixture()
def _mock_deps():
    """Mock database and Redis for equasis endpoint testing."""
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


def _make_mock_session(
    vessel_profile=_VESSEL_PROFILE,
    equasis_data_id=1,
    equasis_uploads=None,
    equasis_upload_detail=None,
):
    """Create a mock async session for equasis tests."""
    mock_session = AsyncMock()
    _insert_call_count = {"count": 0}

    async def execute_side_effect(stmt, *args, **kwargs):
        sql = str(stmt.text) if hasattr(stmt, "text") else str(stmt)
        result_mock = MagicMock()

        if "SELECT * FROM vessel_profiles WHERE mmsi" in sql:
            if vessel_profile:
                row_mock = MagicMock()
                row_mock.__iter__ = MagicMock(return_value=iter(vessel_profile.items()))
                row_mock.keys = MagicMock(return_value=vessel_profile.keys())
                row_mock.__getitem__ = lambda self, key: vessel_profile[key]
                result_mock.mappings.return_value.first.return_value = row_mock
            else:
                result_mock.mappings.return_value.first.return_value = None
            return result_mock

        if "INSERT INTO vessel_profiles" in sql:
            return result_mock

        if "INSERT INTO equasis_data" in sql:
            _insert_call_count["count"] += 1
            row_mock = MagicMock()
            # Return incrementing IDs for multiple inserts
            current_id = equasis_data_id + _insert_call_count["count"] - 1
            row_mock.__getitem__ = lambda self, idx: current_id
            result_mock.first.return_value = row_mock
            return result_mock

        if "UPDATE vessel_profiles SET" in sql:
            return result_mock

        if "SELECT id, upload_timestamp, edition_date" in sql and "equasis_data" in sql:
            if equasis_uploads is not None:
                rows = []
                for u in equasis_uploads:
                    row_mock = MagicMock()
                    row_mock.__iter__ = MagicMock(return_value=iter(u.items()))
                    row_mock.keys = MagicMock(return_value=u.keys())
                    row_mock.__getitem__ = lambda self, key, _u=u: _u[key]
                    rows.append(row_mock)
                result_mock.mappings.return_value.all.return_value = rows
            else:
                result_mock.mappings.return_value.all.return_value = []
            return result_mock

        if "SELECT * FROM equasis_data WHERE id" in sql:
            if equasis_upload_detail:
                row_mock = MagicMock()
                row_mock.__iter__ = MagicMock(return_value=iter(equasis_upload_detail.items()))
                row_mock.keys = MagicMock(return_value=equasis_upload_detail.keys())
                row_mock.__getitem__ = lambda self, key: equasis_upload_detail[key]
                result_mock.mappings.return_value.first.return_value = row_mock
            else:
                result_mock.mappings.return_value.first.return_value = None
            return result_mock

        # Default
        result_mock.scalar.return_value = 0
        result_mock.mappings.return_value.all.return_value = []
        result_mock.mappings.return_value.first.return_value = None
        return result_mock

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)
    mock_session.commit = AsyncMock()
    return mock_session


def _patch_session_and_parser(mock_factory, parsed_pdf=_PARSED_PDF):
    """Return context managers that patch get_session and parse_equasis_pdf."""
    return (
        patch("routes.equasis.get_session", return_value=mock_factory),
        patch("routes.equasis.parse_equasis_pdf", return_value=parsed_pdf),
    )


class TestEquasisUpload:
    """Test POST /api/equasis/upload."""

    def test_upload_valid_pdf_with_matching_mmsi_returns_201(self, _mock_deps):
        """Upload valid PDF with matching mmsi query param returns 201."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session()
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        session_patch, parser_patch = _patch_session_and_parser(mock_factory)
        with session_patch, parser_patch:
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/equasis/upload?mmsi={_VALID_MMSI}",
                    files={"file": ("equasis.pdf", b"fake pdf content", "application/pdf")},
                )

        assert resp.status_code == 201
        body = resp.json()
        assert body["mmsi"] == _VALID_MMSI
        assert body["imo"] == _VALID_IMO
        assert body["ship_name"] == "BLUE"
        assert body["created"] is False
        assert body["equasis_data_id"] == 1
        assert body["summary"]["psc_inspections"] == 32
        assert body["summary"]["flag_changes"] == 14
        assert body["summary"]["companies"] == 17
        assert body["summary"]["classification_entries"] == 2
        assert body["summary"]["name_changes"] == 7

    def test_upload_with_mmsi_mismatch_returns_422(self, _mock_deps):
        """Upload PDF where IMO/MMSI don't match the target vessel returns 422."""
        from fastapi.testclient import TestClient

        # Vessel has different IMO and MMSI than the PDF
        mismatched_vessel = {**_VESSEL_PROFILE, "mmsi": 999999999, "imo": 1111111}
        mock_session = _make_mock_session(vessel_profile=mismatched_vessel)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        session_patch, parser_patch = _patch_session_and_parser(mock_factory)
        with session_patch, parser_patch:
            with TestClient(app) as client:
                resp = client.post(
                    "/api/equasis/upload?mmsi=999999999",
                    files={"file": ("equasis.pdf", b"fake pdf content", "application/pdf")},
                )

        assert resp.status_code == 422
        assert "does not match" in resp.json()["detail"]

    def test_upload_without_mmsi_existing_vessel(self, _mock_deps):
        """Upload without mmsi param, vessel exists — enriches that vessel."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session()
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        session_patch, parser_patch = _patch_session_and_parser(mock_factory)
        with session_patch, parser_patch:
            with TestClient(app) as client:
                resp = client.post(
                    "/api/equasis/upload",
                    files={"file": ("equasis.pdf", b"fake pdf content", "application/pdf")},
                )

        assert resp.status_code == 201
        body = resp.json()
        assert body["mmsi"] == _VALID_MMSI
        assert body["created"] is False

    def test_upload_without_mmsi_new_vessel_creates(self, _mock_deps):
        """Upload without mmsi param, vessel not found — creates new vessel."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session(vessel_profile=None)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        session_patch, parser_patch = _patch_session_and_parser(mock_factory)
        with session_patch, parser_patch:
            with TestClient(app) as client:
                resp = client.post(
                    "/api/equasis/upload",
                    files={"file": ("equasis.pdf", b"fake pdf content", "application/pdf")},
                )

        assert resp.status_code == 201
        body = resp.json()
        assert body["created"] is True
        assert body["mmsi"] == _VALID_MMSI

        # Verify upsert_vessel_profile was called (INSERT INTO vessel_profiles)
        insert_vessel_calls = [
            call for call in mock_session.execute.call_args_list
            if "INSERT INTO vessel_profiles" in str(
                call[0][0].text if hasattr(call[0][0], "text") else call[0][0]
            )
        ]
        assert len(insert_vessel_calls) == 1

    def test_upload_non_pdf_returns_400(self, _mock_deps):
        """Upload a non-PDF file returns 400."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session()
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with patch("routes.equasis.get_session", return_value=mock_factory):
            with patch("routes.equasis.parse_equasis_pdf", side_effect=ValueError("Could not open PDF: not a PDF")):
                with TestClient(app) as client:
                    resp = client.post(
                        "/api/equasis/upload",
                        files={"file": ("document.txt", b"not a pdf", "text/plain")},
                    )

        assert resp.status_code == 400
        assert "Invalid file" in resp.json()["detail"]

    def test_upload_non_equasis_pdf_returns_422(self, _mock_deps):
        """Upload a valid PDF that is not an Equasis Ship Folder returns 422."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session()
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with patch("routes.equasis.get_session", return_value=mock_factory):
            with patch("routes.equasis.parse_equasis_pdf",
                       side_effect=ValueError("Not a valid Equasis Ship Folder PDF")):
                with TestClient(app) as client:
                    resp = client.post(
                        "/api/equasis/upload",
                        files={"file": ("random.pdf", b"fake pdf bytes", "application/pdf")},
                    )

        assert resp.status_code == 422
        assert "Not an Equasis Ship Folder" in resp.json()["detail"]

    def test_vessel_profile_fields_updated_correctly(self, _mock_deps):
        """Vessel profile fields are updated from parsed equasis data."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session()
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        session_patch, parser_patch = _patch_session_and_parser(mock_factory)
        with session_patch, parser_patch:
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/equasis/upload?mmsi={_VALID_MMSI}",
                    files={"file": ("equasis.pdf", b"fake pdf content", "application/pdf")},
                )

        assert resp.status_code == 201

        # Verify UPDATE vessel_profiles was called with the correct extracted fields
        update_calls = [
            call for call in mock_session.execute.call_args_list
            if "UPDATE vessel_profiles SET" in str(
                call[0][0].text if hasattr(call[0][0], "text") else call[0][0]
            )
        ]
        assert len(update_calls) == 1
        update_params = update_calls[0][0][1]
        assert update_params["mmsi"] == _VALID_MMSI
        assert update_params["registered_owner"] == "BLUE SHIPPING LTD"
        assert update_params["technical_manager"] == "MARITIME MANAGEMENT CO"
        assert update_params["operator"] == "GLOBAL SHIP MANAGERS"
        assert update_params["class_society"] == "Lloyd's Register"
        assert update_params["build_year"] == 2001
        assert update_params["dwt"] == 45000
        assert update_params["gross_tonnage"] == 25000
        assert update_params["flag_country"] == "Liberia"
        assert update_params["ship_name"] == "BLUE"
        assert update_params["call_sign"] == "D5FQ7"
        assert update_params["ship_type_text"] == "Bulk Carrier"

    def test_rescoring_event_published_to_redis(self, _mock_deps):
        """Successful upload publishes re-scoring event to Redis."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session()
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        session_patch, parser_patch = _patch_session_and_parser(mock_factory)
        with session_patch, parser_patch:
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/equasis/upload?mmsi={_VALID_MMSI}",
                    files={"file": ("equasis.pdf", b"fake pdf content", "application/pdf")},
                )

        assert resp.status_code == 201
        _mock_deps["redis"].publish.assert_awaited_once()
        call_args = _mock_deps["redis"].publish.call_args
        assert call_args[0][0] == "heimdal:positions"
        event = json.loads(call_args[0][1])
        assert event["mmsis"] == [_VALID_MMSI]
        assert event["count"] == 1

    def test_second_upload_creates_new_equasis_data_row(self, _mock_deps):
        """A second upload creates a new equasis_data row (not overwrite)."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session(equasis_data_id=1)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        session_patch, parser_patch = _patch_session_and_parser(mock_factory)
        with session_patch, parser_patch:
            with TestClient(app) as client:
                resp1 = client.post(
                    f"/api/equasis/upload?mmsi={_VALID_MMSI}",
                    files={"file": ("equasis.pdf", b"fake pdf content", "application/pdf")},
                )
                resp2 = client.post(
                    f"/api/equasis/upload?mmsi={_VALID_MMSI}",
                    files={"file": ("equasis2.pdf", b"fake pdf content 2", "application/pdf")},
                )

        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["equasis_data_id"] == 1
        assert resp2.json()["equasis_data_id"] == 2

        # Verify two INSERT INTO equasis_data calls were made
        insert_calls = [
            call for call in mock_session.execute.call_args_list
            if "INSERT INTO equasis_data" in str(
                call[0][0].text if hasattr(call[0][0], "text") else call[0][0]
            )
        ]
        assert len(insert_calls) == 2

    def test_upload_mmsi_not_found_returns_404(self, _mock_deps):
        """Upload with mmsi param that doesn't exist returns 404."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session(vessel_profile=None)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        session_patch, parser_patch = _patch_session_and_parser(mock_factory)
        with session_patch, parser_patch:
            with TestClient(app) as client:
                resp = client.post(
                    "/api/equasis/upload?mmsi=999999999",
                    files={"file": ("equasis.pdf", b"fake pdf content", "application/pdf")},
                )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Vessel not found"


class TestEquasisHistory:
    """Test GET /api/equasis/{mmsi}/history."""

    def test_get_history_returns_uploads(self, _mock_deps):
        """GET history returns list of uploads for the vessel."""
        from fastapi.testclient import TestClient

        uploads = [
            {"id": 1, "upload_timestamp": "2026-03-13T10:00:00", "edition_date": "13/03/2026"},
            {"id": 2, "upload_timestamp": "2026-03-12T10:00:00", "edition_date": "12/03/2026"},
        ]
        mock_session = _make_mock_session(equasis_uploads=uploads)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with patch("routes.equasis.get_session", return_value=mock_factory):
            with TestClient(app) as client:
                resp = client.get(f"/api/equasis/{_VALID_MMSI}/history")

        assert resp.status_code == 200
        body = resp.json()
        assert body["mmsi"] == _VALID_MMSI
        assert len(body["uploads"]) == 2


class TestEquasisUploadDetail:
    """Test GET /api/equasis/{mmsi}/upload/{upload_id}."""

    def test_get_upload_detail_returns_data(self, _mock_deps):
        """GET upload detail returns the full equasis data row."""
        from fastapi.testclient import TestClient

        detail = {
            "id": 1,
            "mmsi": _VALID_MMSI,
            "imo": _VALID_IMO,
            "upload_timestamp": "2026-03-13T10:00:00",
            "edition_date": "13/03/2026",
            "ship_particulars": {},
            "management": [],
        }
        mock_session = _make_mock_session(equasis_upload_detail=detail)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with patch("routes.equasis.get_session", return_value=mock_factory):
            with TestClient(app) as client:
                resp = client.get(f"/api/equasis/{_VALID_MMSI}/upload/1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 1
        assert body["mmsi"] == _VALID_MMSI

    def test_get_upload_detail_not_found_returns_404(self, _mock_deps):
        """GET upload detail for nonexistent upload returns 404."""
        from fastapi.testclient import TestClient

        mock_session = _make_mock_session(equasis_upload_detail=None)
        mock_factory = _FakeSessionFactory(mock_session)

        app = api_main.create_app()
        with patch("routes.equasis.get_session", return_value=mock_factory):
            with TestClient(app) as client:
                resp = client.get(f"/api/equasis/{_VALID_MMSI}/upload/999")

        assert resp.status_code == 404
