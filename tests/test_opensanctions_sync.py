"""Tests for services/opensanctions/sync.py daily sync service.

Tests download, sync flow, and no-deletion behavior with mocks.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.opensanctions.sync import download_dataset, run_sync, DOWNLOAD_SCRIPT


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_ndjson(tmp_path: Path) -> Path:
    """Create a small NDJSON fixture."""
    entities = [
        {
            "id": "v1", "schema": "Vessel",
            "properties": {"name": ["TEST VESSEL"], "imoNumber": ["1234567"]},
            "target": True, "datasets": ["os"],
        },
        {
            "id": "c1", "schema": "Company",
            "properties": {"name": ["Test Corp"]},
            "target": False, "datasets": ["os"],
        },
        {
            "id": "o1", "schema": "Ownership",
            "properties": {"owner": ["c1"], "asset": ["v1"]},
            "target": False, "datasets": ["os"],
        },
    ]
    filepath = tmp_path / "default.json"
    with open(filepath, "w") as f:
        for e in entities:
            f.write(json.dumps(e) + "\n")
    return filepath


# ---------------------------------------------------------------------------
# Tests: download_dataset
# ---------------------------------------------------------------------------

class TestDownloadDataset:
    @patch("services.opensanctions.sync.subprocess.run")
    def test_download_calls_script(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="Done", stderr="")
        # Create the file that download would produce
        (tmp_path / "default.json").write_text("{}")

        result = download_dataset(str(tmp_path))
        assert result == tmp_path / "default.json"

        # Verify the bash script was called
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert str(DOWNLOAD_SCRIPT) in call_args[0][0]

    @patch("services.opensanctions.sync.subprocess.run")
    def test_download_failure_raises(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="curl failed")
        with pytest.raises(RuntimeError, match="Download failed"):
            download_dataset(str(tmp_path))

    @patch("services.opensanctions.sync.subprocess.run")
    def test_download_missing_file_raises(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="Done", stderr="")
        # Don't create the file
        with pytest.raises(FileNotFoundError):
            download_dataset(str(tmp_path))


# ---------------------------------------------------------------------------
# Tests: run_sync
# ---------------------------------------------------------------------------

class TestRunSync:
    @patch("services.opensanctions.sync.psycopg2")
    def test_sync_processes_file(self, mock_psycopg2, sample_ndjson):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        totals = run_sync(
            db_url="postgresql://test@localhost/test",
            data_dir=str(sample_ndjson.parent),
            skip_download=True,
        )

        assert totals["entities"] == 2   # Vessel + Company
        assert totals["relationships"] == 1  # Ownership
        assert totals["vessel_links"] == 1   # IMO link
        mock_conn.commit.assert_called()
        mock_conn.close.assert_called_once()

    @patch("services.opensanctions.sync.psycopg2")
    def test_sync_converts_asyncpg_url(self, mock_psycopg2, sample_ndjson):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        run_sync(
            db_url="postgresql+asyncpg://test@localhost/test",
            data_dir=str(sample_ndjson.parent),
            skip_download=True,
        )

        mock_psycopg2.connect.assert_called_once_with("postgresql://test@localhost/test")

    @patch("services.opensanctions.sync.psycopg2")
    def test_sync_skip_download_missing_file_raises(self, mock_psycopg2, tmp_path):
        with pytest.raises(FileNotFoundError):
            run_sync(
                db_url="postgresql://test@localhost/test",
                data_dir=str(tmp_path),
                skip_download=True,
            )

    @patch("services.opensanctions.sync.psycopg2")
    def test_entities_not_deleted_on_rerun(self, mock_psycopg2, tmp_path):
        """Running sync with a smaller dataset does NOT delete old entities.

        We verify this by checking that only INSERT ... ON CONFLICT UPDATE
        is used, never DELETE.
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        # First run with 2 entities
        filepath = tmp_path / "default.json"
        entities = [
            {"id": "v1", "schema": "Vessel", "properties": {"name": ["A"]}, "target": False, "datasets": ["os"]},
            {"id": "v2", "schema": "Vessel", "properties": {"name": ["B"]}, "target": False, "datasets": ["os"]},
        ]
        with open(filepath, "w") as f:
            for e in entities:
                f.write(json.dumps(e) + "\n")

        run_sync(db_url="postgresql://test@localhost/test", data_dir=str(tmp_path), skip_download=True)

        # Second run with only 1 entity (v2 removed from dataset)
        with open(filepath, "w") as f:
            f.write(json.dumps(entities[0]) + "\n")

        run_sync(db_url="postgresql://test@localhost/test", data_dir=str(tmp_path), skip_download=True)

        # Verify no DELETE was ever called
        for call_obj in mock_cursor.execute.call_args_list:
            sql = str(call_obj[0][0])
            assert "DELETE" not in sql.upper(), f"Unexpected DELETE in SQL: {sql}"

    @patch("services.opensanctions.sync.psycopg2")
    def test_sync_updates_last_seen(self, mock_psycopg2, sample_ndjson):
        """Entities that exist in the new dataset get last_seen updated."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        run_sync(
            db_url="postgresql://test@localhost/test",
            data_dir=str(sample_ndjson.parent),
            skip_download=True,
        )

        # Verify ON CONFLICT UPDATE includes last_seen = NOW()
        entity_calls = [
            c for c in mock_cursor.execute.call_args_list
            if "os_entities" in str(c)
        ]
        assert len(entity_calls) > 0
        sql = entity_calls[0][0][0]
        assert "last_seen = NOW()" in sql


# ---------------------------------------------------------------------------
# Tests: Dockerfile exists
# ---------------------------------------------------------------------------

def test_dockerfile_exists():
    dockerfile = PROJECT_ROOT / "services" / "opensanctions" / "Dockerfile"
    assert dockerfile.exists(), "Dockerfile for opensanctions sync service is missing"
