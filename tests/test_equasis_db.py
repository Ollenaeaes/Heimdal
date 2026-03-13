"""Tests for Equasis data database schema and repository functions.

Verifies:
- Migration SQL is valid (table name, column names, indexes)
- insert_equasis_data creates a row and returns an id
- get_latest_equasis_data returns the most recent upload
- Multiple uploads for same vessel create separate rows
- update_vessel_profile_from_equasis updates the right fields
- list_equasis_uploads returns summary data ordered by timestamp DESC
- get_equasis_upload_by_id returns the right row
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from shared.db.repositories import (
    get_equasis_upload_by_id,
    get_latest_equasis_data,
    insert_equasis_data,
    list_equasis_uploads,
    update_vessel_profile_from_equasis,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "db" / "migrations" / "010_equasis_data.sql"


def _make_mock_session(rows: list[dict[str, Any]] | None = None, scalar: Any = None):
    """Create an AsyncMock session that returns configurable results."""
    session = AsyncMock()
    result_mock = MagicMock()

    if rows is not None:
        mappings_mock = MagicMock()
        mapping_rows = []
        for r in rows:
            row_mock = MagicMock()
            row_mock.__iter__ = lambda s, _r=r: iter(_r.items())
            row_mock.keys = lambda _r=r: _r.keys()
            row_mock.__getitem__ = lambda s, k, _r=r: _r[k]
            row_mock.items = lambda _r=r: _r.items()
            mapping_rows.append(row_mock)
        mappings_mock.all.return_value = mapping_rows
        mappings_mock.first.return_value = mapping_rows[0] if mapping_rows else None
        result_mock.mappings.return_value = mappings_mock

    if scalar is not None:
        first_mock = MagicMock()
        first_mock.__getitem__ = lambda s, i: scalar if i == 0 else None
        result_mock.first.return_value = first_mock
    elif rows is None:
        result_mock.first.return_value = None
        mappings_mock = MagicMock()
        mappings_mock.first.return_value = None
        mappings_mock.all.return_value = []
        result_mock.mappings.return_value = mappings_mock

    session.execute.return_value = result_mock
    return session


# ---------------------------------------------------------------------------
# Migration SQL validation
# ---------------------------------------------------------------------------


class TestMigrationSQL:
    """Verify the migration file is valid and contains expected definitions."""

    def test_migration_file_exists(self):
        assert MIGRATION_PATH.exists(), f"Migration file not found: {MIGRATION_PATH}"

    def test_creates_equasis_data_table(self):
        sql = MIGRATION_PATH.read_text()
        assert "CREATE TABLE IF NOT EXISTS equasis_data" in sql

    def test_has_expected_columns(self):
        sql = MIGRATION_PATH.read_text()
        expected_columns = [
            "id", "mmsi", "imo", "upload_timestamp", "edition_date",
            "ship_particulars", "management", "classification_status",
            "classification_surveys", "safety_certificates", "psc_inspections",
            "name_history", "flag_history", "company_history", "raw_extracted",
        ]
        for col in expected_columns:
            assert col in sql, f"Missing column: {col}"

    def test_mmsi_references_vessel_profiles(self):
        sql = MIGRATION_PATH.read_text()
        assert "REFERENCES vessel_profiles(mmsi)" in sql

    def test_has_mmsi_index(self):
        sql = MIGRATION_PATH.read_text()
        assert "idx_equasis_data_mmsi" in sql

    def test_has_mmsi_latest_index(self):
        sql = MIGRATION_PATH.read_text()
        assert "idx_equasis_data_mmsi_latest" in sql
        assert "upload_timestamp DESC" in sql

    def test_jsonb_defaults(self):
        sql = MIGRATION_PATH.read_text()
        # JSONB columns that hold objects default to '{}'
        assert "ship_particulars        JSONB DEFAULT '{}'" in sql
        assert "raw_extracted           JSONB DEFAULT '{}'" in sql
        # JSONB columns that hold arrays default to '[]'
        assert "management              JSONB DEFAULT '[]'" in sql


# ---------------------------------------------------------------------------
# insert_equasis_data tests
# ---------------------------------------------------------------------------


class TestInsertEquasisData:
    """Tests for inserting equasis data rows."""

    @pytest.mark.asyncio
    async def test_returns_id(self):
        """Should return the new row id."""
        session = _make_mock_session(scalar=42)
        data = {
            "mmsi": 123456789, "imo": 9876543,
            "upload_timestamp": "2024-01-15T10:00:00Z",
            "edition_date": "2024-01-10",
            "ship_particulars": "{}", "management": "[]",
            "classification_status": "[]", "classification_surveys": "[]",
            "safety_certificates": "[]", "psc_inspections": "[]",
            "name_history": "[]", "flag_history": "[]",
            "company_history": "[]", "raw_extracted": "{}",
        }
        result = await insert_equasis_data(session, data)
        assert result == 42

    @pytest.mark.asyncio
    async def test_sql_has_returning_id(self):
        """SQL should use RETURNING id."""
        session = _make_mock_session(scalar=1)
        data = {
            "mmsi": 123456789, "imo": None,
            "upload_timestamp": None, "edition_date": None,
            "ship_particulars": "{}", "management": "[]",
            "classification_status": "[]", "classification_surveys": "[]",
            "safety_certificates": "[]", "psc_inspections": "[]",
            "name_history": "[]", "flag_history": "[]",
            "company_history": "[]", "raw_extracted": "{}",
        }
        await insert_equasis_data(session, data)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "RETURNING id" in sql_text

    @pytest.mark.asyncio
    async def test_sql_inserts_all_columns(self):
        """SQL should reference all equasis_data columns."""
        session = _make_mock_session(scalar=1)
        data = {
            "mmsi": 123456789, "imo": None,
            "upload_timestamp": None, "edition_date": None,
            "ship_particulars": "{}", "management": "[]",
            "classification_status": "[]", "classification_surveys": "[]",
            "safety_certificates": "[]", "psc_inspections": "[]",
            "name_history": "[]", "flag_history": "[]",
            "company_history": "[]", "raw_extracted": "{}",
        }
        await insert_equasis_data(session, data)

        sql_text = str(session.execute.call_args[0][0].text)
        for col in ["mmsi", "imo", "upload_timestamp", "edition_date",
                     "ship_particulars", "management", "classification_status",
                     "classification_surveys", "safety_certificates",
                     "psc_inspections", "name_history", "flag_history",
                     "company_history", "raw_extracted"]:
            assert col in sql_text, f"Missing column in INSERT: {col}"

    @pytest.mark.asyncio
    async def test_passes_data_as_params(self):
        """Data dict should be passed as parameters."""
        session = _make_mock_session(scalar=1)
        data = {
            "mmsi": 123456789, "imo": 9876543,
            "upload_timestamp": "2024-01-15T10:00:00Z",
            "edition_date": "2024-01-10",
            "ship_particulars": "{}", "management": "[]",
            "classification_status": "[]", "classification_surveys": "[]",
            "safety_certificates": "[]", "psc_inspections": "[]",
            "name_history": "[]", "flag_history": "[]",
            "company_history": "[]", "raw_extracted": "{}",
        }
        await insert_equasis_data(session, data)

        params = session.execute.call_args[0][1]
        assert params["mmsi"] == 123456789
        assert params["imo"] == 9876543

    @pytest.mark.asyncio
    async def test_returns_zero_on_none_row(self):
        """If first() returns None, should return 0."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.first.return_value = None
        session.execute.return_value = result_mock

        data = {
            "mmsi": 123456789, "imo": None,
            "upload_timestamp": None, "edition_date": None,
            "ship_particulars": "{}", "management": "[]",
            "classification_status": "[]", "classification_surveys": "[]",
            "safety_certificates": "[]", "psc_inspections": "[]",
            "name_history": "[]", "flag_history": "[]",
            "company_history": "[]", "raw_extracted": "{}",
        }
        result = await insert_equasis_data(session, data)
        assert result == 0


# ---------------------------------------------------------------------------
# get_latest_equasis_data tests
# ---------------------------------------------------------------------------


class TestGetLatestEquasisData:
    """Tests for retrieving the latest equasis data for a vessel."""

    @pytest.mark.asyncio
    async def test_returns_dict_when_found(self):
        """Should return a dict when data exists."""
        rows = [{"id": 1, "mmsi": 123456789, "imo": 9876543, "upload_timestamp": "2024-01-15"}]
        session = _make_mock_session(rows=rows)
        result = await get_latest_equasis_data(session, mmsi=123456789)
        assert result is not None
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        """Should return None when no data exists."""
        session = _make_mock_session()
        result = await get_latest_equasis_data(session, mmsi=999999999)
        assert result is None

    @pytest.mark.asyncio
    async def test_sql_orders_by_timestamp_desc_limit_1(self):
        """SQL should order by upload_timestamp DESC and LIMIT 1."""
        session = _make_mock_session()
        await get_latest_equasis_data(session, mmsi=123456789)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "ORDER BY upload_timestamp DESC" in sql_text
        assert "LIMIT 1" in sql_text

    @pytest.mark.asyncio
    async def test_filters_by_mmsi(self):
        """SQL should filter by mmsi parameter."""
        session = _make_mock_session()
        await get_latest_equasis_data(session, mmsi=123456789)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "WHERE mmsi = :mmsi" in sql_text
        params = session.execute.call_args[0][1]
        assert params["mmsi"] == 123456789


# ---------------------------------------------------------------------------
# Multiple uploads for same vessel
# ---------------------------------------------------------------------------


class TestMultipleUploads:
    """Verify that insert_equasis_data can be called multiple times for the same vessel."""

    @pytest.mark.asyncio
    async def test_multiple_inserts_call_execute_each_time(self):
        """Each insert should call session.execute independently."""
        session = _make_mock_session(scalar=1)

        base_data = {
            "mmsi": 123456789, "imo": 9876543,
            "upload_timestamp": None, "edition_date": None,
            "ship_particulars": "{}", "management": "[]",
            "classification_status": "[]", "classification_surveys": "[]",
            "safety_certificates": "[]", "psc_inspections": "[]",
            "name_history": "[]", "flag_history": "[]",
            "company_history": "[]", "raw_extracted": "{}",
        }

        # Reset scalar for second call
        first_mock = MagicMock()
        second_mock = MagicMock()
        first_mock.__getitem__ = lambda s, i: 1 if i == 0 else None
        second_mock.__getitem__ = lambda s, i: 2 if i == 0 else None

        result_mock_1 = MagicMock()
        result_mock_1.first.return_value = first_mock
        result_mock_2 = MagicMock()
        result_mock_2.first.return_value = second_mock

        session.execute.side_effect = [result_mock_1, result_mock_2]

        id1 = await insert_equasis_data(session, {**base_data, "upload_timestamp": "2024-01-01"})
        id2 = await insert_equasis_data(session, {**base_data, "upload_timestamp": "2024-02-01"})

        assert id1 == 1
        assert id2 == 2
        assert session.execute.call_count == 2


# ---------------------------------------------------------------------------
# list_equasis_uploads tests
# ---------------------------------------------------------------------------


class TestListEquasisUploads:
    """Tests for listing equasis upload summaries."""

    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
        """Should return a list of dicts."""
        rows = [
            {"id": 2, "upload_timestamp": "2024-02-15", "edition_date": "2024-02-10"},
            {"id": 1, "upload_timestamp": "2024-01-15", "edition_date": "2024-01-10"},
        ]
        session = _make_mock_session(rows=rows)
        result = await list_equasis_uploads(session, mmsi=123456789)
        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none(self):
        """Should return empty list when no uploads exist."""
        session = _make_mock_session(rows=[])
        result = await list_equasis_uploads(session, mmsi=999999999)
        assert result == []

    @pytest.mark.asyncio
    async def test_sql_selects_summary_fields_only(self):
        """SQL should select only id, upload_timestamp, edition_date."""
        session = _make_mock_session(rows=[])
        await list_equasis_uploads(session, mmsi=123456789)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "id" in sql_text
        assert "upload_timestamp" in sql_text
        assert "edition_date" in sql_text
        # Should not select all columns
        assert "SELECT *" not in sql_text

    @pytest.mark.asyncio
    async def test_sql_orders_by_timestamp_desc(self):
        """SQL should order by upload_timestamp DESC."""
        session = _make_mock_session(rows=[])
        await list_equasis_uploads(session, mmsi=123456789)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "ORDER BY upload_timestamp DESC" in sql_text

    @pytest.mark.asyncio
    async def test_filters_by_mmsi(self):
        """SQL should filter by mmsi."""
        session = _make_mock_session(rows=[])
        await list_equasis_uploads(session, mmsi=123456789)

        params = session.execute.call_args[0][1]
        assert params["mmsi"] == 123456789


# ---------------------------------------------------------------------------
# get_equasis_upload_by_id tests
# ---------------------------------------------------------------------------


class TestGetEquasisUploadById:
    """Tests for retrieving a specific equasis upload."""

    @pytest.mark.asyncio
    async def test_returns_dict_when_found(self):
        """Should return a dict when the upload exists."""
        rows = [{"id": 5, "mmsi": 123456789, "imo": 9876543}]
        session = _make_mock_session(rows=rows)
        result = await get_equasis_upload_by_id(session, upload_id=5)
        assert result is not None
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        """Should return None when the upload doesn't exist."""
        session = _make_mock_session()
        result = await get_equasis_upload_by_id(session, upload_id=999)
        assert result is None

    @pytest.mark.asyncio
    async def test_sql_filters_by_id(self):
        """SQL should filter by id parameter."""
        session = _make_mock_session()
        await get_equasis_upload_by_id(session, upload_id=42)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "WHERE id = :upload_id" in sql_text
        params = session.execute.call_args[0][1]
        assert params["upload_id"] == 42


# ---------------------------------------------------------------------------
# update_vessel_profile_from_equasis tests
# ---------------------------------------------------------------------------


class TestUpdateVesselProfileFromEquasis:
    """Tests for updating vessel profiles from equasis data."""

    @pytest.mark.asyncio
    async def test_updates_provided_fields(self):
        """Should generate SET clauses for non-None fields."""
        session = _make_mock_session()
        equasis = {
            "registered_owner": "Acme Shipping Ltd",
            "technical_manager": "Global Ship Management",
            "class_society": "Lloyd's Register",
        }
        await update_vessel_profile_from_equasis(session, mmsi=123456789, equasis_data=equasis)

        session.execute.assert_called_once()
        sql_text = str(session.execute.call_args[0][0].text)
        assert "UPDATE vessel_profiles SET" in sql_text
        assert "registered_owner = :registered_owner" in sql_text
        assert "technical_manager = :technical_manager" in sql_text
        assert "class_society = :class_society" in sql_text
        assert "updated_at = NOW()" in sql_text
        assert "WHERE mmsi = :mmsi" in sql_text

        params = session.execute.call_args[0][1]
        assert params["mmsi"] == 123456789
        assert params["registered_owner"] == "Acme Shipping Ltd"
        assert params["technical_manager"] == "Global Ship Management"
        assert params["class_society"] == "Lloyd's Register"

    @pytest.mark.asyncio
    async def test_skips_none_fields(self):
        """Should not include None fields in the SET clause."""
        session = _make_mock_session()
        equasis = {
            "registered_owner": "Acme Shipping Ltd",
            "technical_manager": None,
            "operator": None,
            "build_year": 2010,
        }
        await update_vessel_profile_from_equasis(session, mmsi=123456789, equasis_data=equasis)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "registered_owner = :registered_owner" in sql_text
        assert "build_year = :build_year" in sql_text
        assert "technical_manager" not in sql_text
        assert "operator" not in sql_text

        params = session.execute.call_args[0][1]
        assert "technical_manager" not in params
        assert "operator" not in params

    @pytest.mark.asyncio
    async def test_no_execute_when_all_none(self):
        """Should not call execute when all fields are None."""
        session = _make_mock_session()
        equasis = {
            "registered_owner": None,
            "technical_manager": None,
        }
        await update_vessel_profile_from_equasis(session, mmsi=123456789, equasis_data=equasis)

        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_execute_when_empty_dict(self):
        """Should not call execute when equasis_data is empty."""
        session = _make_mock_session()
        await update_vessel_profile_from_equasis(session, mmsi=123456789, equasis_data={})

        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_supported_fields(self):
        """Should support all 13 fields from the spec."""
        session = _make_mock_session()
        equasis = {
            "registered_owner": "Owner Co",
            "technical_manager": "Manager Co",
            "operator": "Operator Co",
            "class_society": "DNV",
            "build_year": 2015,
            "dwt": 50000,
            "gross_tonnage": 30000,
            "flag_country": "Panama",
            "ship_name": "MV Test Vessel",
            "call_sign": "ABCD1",
            "ship_type_text": "Bulk Carrier",
            "length": 200.5,
            "width": 32.2,
        }
        await update_vessel_profile_from_equasis(session, mmsi=123456789, equasis_data=equasis)

        sql_text = str(session.execute.call_args[0][0].text)
        params = session.execute.call_args[0][1]

        for field in equasis:
            assert f"{field} = :{field}" in sql_text, f"Missing field in SQL: {field}"
            assert params[field] == equasis[field], f"Wrong param for {field}"

    @pytest.mark.asyncio
    async def test_always_includes_updated_at(self):
        """Should always set updated_at = NOW() when updating."""
        session = _make_mock_session()
        equasis = {"ship_name": "Updated Name"}
        await update_vessel_profile_from_equasis(session, mmsi=123456789, equasis_data=equasis)

        sql_text = str(session.execute.call_args[0][0].text)
        assert "updated_at = NOW()" in sql_text
