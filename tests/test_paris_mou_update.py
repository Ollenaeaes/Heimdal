"""Tests for the incremental Paris MoU update service."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Load the module from file path since the directory has a hyphen
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = PROJECT_ROOT / "services" / "paris-mou" / "update.py"

spec = importlib.util.spec_from_file_location("paris_mou_update", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules["paris_mou_update"] = mod
spec.loader.exec_module(mod)

CREATE_DOWNLOAD_LOG_SQL = mod.CREATE_DOWNLOAD_LOG_SQL
get_processed_files = mod.get_processed_files
parse_response = mod.parse_response
record_download = mod.record_download
ensure_tracking_table = mod.ensure_tracking_table
insert_inspections = mod.insert_inspections
process_file = mod.process_file
main = mod.main


class TestCreateTableSQL:
    """Verify the psc_download_log CREATE TABLE SQL is correct."""

    def test_sql_creates_table_if_not_exists(self):
        assert "CREATE TABLE IF NOT EXISTS psc_download_log" in CREATE_DOWNLOAD_LOG_SQL

    def test_sql_has_filename_primary_key(self):
        assert "filename VARCHAR(255) PRIMARY KEY" in CREATE_DOWNLOAD_LOG_SQL

    def test_sql_has_downloaded_at_with_default(self):
        assert "downloaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()" in CREATE_DOWNLOAD_LOG_SQL

    def test_sql_has_record_count(self):
        assert "record_count INTEGER" in CREATE_DOWNLOAD_LOG_SQL

    def test_sql_has_status_with_default(self):
        assert "status VARCHAR(20) NOT NULL DEFAULT 'completed'" in CREATE_DOWNLOAD_LOG_SQL


class TestGetProcessedFiles:
    """Test that get_processed_files returns a set of filenames from DB."""

    def test_returns_set_of_filenames(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [
            ("GetPublicFile_2024_01.xml",),
            ("GetPublicFile_2024_02.xml",),
            ("GetPublicFile_2024_03.xml",),
        ]

        result = get_processed_files(mock_conn)

        assert result == {
            "GetPublicFile_2024_01.xml",
            "GetPublicFile_2024_02.xml",
            "GetPublicFile_2024_03.xml",
        }

    def test_returns_empty_set_when_no_files(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []

        result = get_processed_files(mock_conn)

        assert result == set()

    def test_only_returns_completed_files(self):
        """Verify the SQL filters on status = 'completed'."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [("file1.xml",)]

        get_processed_files(mock_conn)

        executed_sql = mock_cursor.execute.call_args[0][0]
        assert "status = 'completed'" in executed_sql


class TestNewFileDetection:
    """Test the diff logic: new files = API list - already processed."""

    def test_detects_new_files(self):
        remote_files = [
            "GetPublicFile_2024_01.xml",
            "GetPublicFile_2024_02.xml",
            "GetPublicFile_2024_03.xml",
            "GetPublicFile_2024_04.xml",
        ]
        already_processed = {
            "GetPublicFile_2024_01.xml",
            "GetPublicFile_2024_02.xml",
        }

        new_files = [f for f in remote_files if f not in already_processed]

        assert new_files == [
            "GetPublicFile_2024_03.xml",
            "GetPublicFile_2024_04.xml",
        ]

    def test_no_new_files_when_all_processed(self):
        remote_files = [
            "GetPublicFile_2024_01.xml",
            "GetPublicFile_2024_02.xml",
        ]
        already_processed = {
            "GetPublicFile_2024_01.xml",
            "GetPublicFile_2024_02.xml",
        }

        new_files = [f for f in remote_files if f not in already_processed]

        assert new_files == []

    def test_all_new_when_nothing_processed(self):
        remote_files = [
            "GetPublicFile_2024_01.xml",
            "GetPublicFile_2024_02.xml",
        ]
        already_processed = set()

        new_files = [f for f in remote_files if f not in already_processed]

        assert len(new_files) == 2


class TestGracefulNoOp:
    """Test that the script handles no new files gracefully."""

    @patch.object(mod, "get_file_list")
    @patch.object(mod, "get_auth_token")
    @patch.object(mod, "get_processed_files")
    @patch.object(mod, "ensure_tracking_table")
    @patch.object(mod, "psycopg2")
    @patch.dict("os.environ", {"PARIS_MOU_KEY": "test-key", "DATABASE_URL": "postgres://localhost/test"})
    def test_exits_cleanly_when_no_new_files(
        self, mock_psycopg2, mock_ensure, mock_get_processed, mock_auth, mock_filelist
    ):
        mock_conn = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn

        mock_get_processed.return_value = {"GetPublicFile_2024_01.xml"}
        mock_auth.return_value = "test-token"
        mock_filelist.return_value = ["GetPublicFile_2024_01.xml"]

        # Should complete without error
        main()

        # Verify connection was closed
        mock_conn.close.assert_called_once()


class TestModuleImports:
    """Test that the module imports without errors."""

    def test_module_has_expected_attributes(self):
        assert hasattr(mod, "main")
        assert hasattr(mod, "get_processed_files")
        assert hasattr(mod, "ensure_tracking_table")
        assert hasattr(mod, "record_download")
        assert hasattr(mod, "insert_inspections")
        assert hasattr(mod, "process_file")
        assert hasattr(mod, "CREATE_DOWNLOAD_LOG_SQL")

    def test_parse_response_json(self):
        result = parse_response('{"status": {"code": "success"}, "files": ["a.xml"]}')
        assert result["status"]["code"] == "success"
        assert result["files"] == ["a.xml"]

    def test_parse_response_php(self):
        php_text = """Array
(
    [status] => Array
        (
            [code] => success
            [message] => Token generated
        )
    [access_token] => abc123
    [source_ip] => 1.2.3.4
)"""
        result = parse_response(php_text)
        assert result["status"]["code"] == "success"
        assert result["access_token"] == "abc123"
        assert result["source_ip"] == "1.2.3.4"
