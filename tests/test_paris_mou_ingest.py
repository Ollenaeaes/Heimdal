"""Tests for the Paris MoU batch ingest script.

Simple unit tests that don't require a database connection.
"""

import json
import sys
from pathlib import Path

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ingest_paris_mou import (
    build_arg_parser,
    filter_inspection_files,
    parse_response,
)


class TestParseResponse:
    """Test the parse_response function handles JSON and PHP print_r formats."""

    def test_parses_valid_json(self):
        raw = json.dumps({
            "status": {"code": "success", "message": "OK"},
            "access_token": "abc123",
        })
        result = parse_response(raw)
        assert result["status"]["code"] == "success"
        assert result["access_token"] == "abc123"

    def test_parses_php_print_r_with_token(self):
        raw = (
            "Array\n"
            "(\n"
            "    [code] => success\n"
            "    [message] => Authorization granted\n"
            "    [access_token] => tok_xyz789\n"
            "    [source_ip] => 1.2.3.4\n"
            ")\n"
        )
        result = parse_response(raw)
        assert result["status"]["code"] == "success"
        assert result["status"]["message"] == "Authorization granted"
        assert result["access_token"] == "tok_xyz789"
        assert result["source_ip"] == "1.2.3.4"

    def test_parses_php_print_r_file_list(self):
        raw = (
            "Array\n"
            "(\n"
            "    [code] => success\n"
            "    [message] => Files listed\n"
            "    [0] => GetPublicFile_20240101_daily.xml.zip\n"
            "    [1] => 1234\n"
            "    [2] => GetPublicFile_20240102_daily.xml.zip\n"
            "    [3] => 5678\n"
            ")\n"
        )
        result = parse_response(raw)
        assert result["status"]["code"] == "success"
        assert "files" in result
        assert "GetPublicFile_20240101_daily.xml.zip" in result["files"]

    def test_parses_php_print_r_failure(self):
        raw = (
            "Array\n"
            "(\n"
            "    [code] => error\n"
            "    [message] => Invalid token\n"
            ")\n"
        )
        result = parse_response(raw)
        assert result["status"]["code"] == "error"
        assert result["status"]["message"] == "Invalid token"

    def test_handles_empty_json_object(self):
        result = parse_response("{}")
        assert result == {}

    def test_handles_garbage_input(self):
        result = parse_response("not json and not php either")
        assert result["status"]["code"] == "unknown"


class TestFilterInspectionFiles:
    """Test file filtering correctly selects GetPublicFile_* pattern."""

    def test_filters_inspection_files(self):
        files = [
            "GetPublicFile_20240101_daily.xml.zip",
            "GetPublicFile_20240102_daily.xml.zip",
            "SomeOtherFile_20240101.xml",
            "GetDetentionFile_20240101.xml",
            "GetPublicFile_20230601_full.xml.zip",
        ]
        result = filter_inspection_files(files)
        assert len(result) == 3
        assert all(f.startswith("GetPublicFile_") for f in result)

    def test_returns_empty_for_no_matches(self):
        files = ["SomeOther.xml", "Detention_20240101.xml"]
        result = filter_inspection_files(files)
        assert result == []

    def test_handles_empty_list(self):
        assert filter_inspection_files([]) == []


class TestArgParser:
    """Test CLI argument parsing."""

    def test_dry_run_flag(self):
        parser = build_arg_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_file_flag(self):
        parser = build_arg_parser()
        args = parser.parse_args(["--file", "/tmp/test.xml"])
        assert args.file == "/tmp/test.xml"

    def test_download_only_flag(self):
        parser = build_arg_parser()
        args = parser.parse_args(["--download-only"])
        assert args.download_only is True

    def test_db_url_flag(self):
        parser = build_arg_parser()
        args = parser.parse_args(["--db-url", "postgres://localhost/test"])
        assert args.db_url == "postgres://localhost/test"

    def test_data_dir_flag(self):
        parser = build_arg_parser()
        args = parser.parse_args(["--data-dir", "/tmp/paris_mou"])
        assert args.data_dir == "/tmp/paris_mou"

    def test_defaults(self):
        parser = build_arg_parser()
        args = parser.parse_args([])
        assert args.dry_run is False
        assert args.file is None
        assert args.download_only is False
        assert args.db_url is None
        assert args.data_dir is None

    def test_combined_flags(self):
        parser = build_arg_parser()
        args = parser.parse_args(["--dry-run", "--file", "/tmp/data.xml"])
        assert args.dry_run is True
        assert args.file == "/tmp/data.xml"


class TestInsertSQL:
    """Test that the batch insert SQL uses ON CONFLICT DO NOTHING."""

    def test_inspection_sql_has_on_conflict(self):
        # Import the function and inspect its source
        from scripts.ingest_paris_mou import insert_inspections_batch
        import inspect
        source = inspect.getsource(insert_inspections_batch)
        assert "ON CONFLICT (inspection_id) DO NOTHING" in source

    def test_inspection_sql_has_returning_id(self):
        from scripts.ingest_paris_mou import insert_inspections_batch
        import inspect
        source = inspect.getsource(insert_inspections_batch)
        assert "RETURNING id" in source


class TestModuleImport:
    """Test that the script module can be imported without errors."""

    def test_import_succeeds(self):
        import scripts.ingest_paris_mou as mod
        assert hasattr(mod, "main")
        assert hasattr(mod, "parse_response")
        assert hasattr(mod, "filter_inspection_files")
        assert hasattr(mod, "insert_inspections_batch")
        assert hasattr(mod, "process_file")
