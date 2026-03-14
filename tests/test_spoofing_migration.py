"""Tests for the 012_spoofing_tables migration SQL."""

from pathlib import Path

import pytest


MIGRATION_PATH = Path(__file__).parent.parent / "db" / "migrations" / "012_spoofing_tables.sql"


class TestMigrationFile:
    """Verify the migration SQL file structure."""

    def test_migration_file_exists(self):
        assert MIGRATION_PATH.exists(), "Migration file 012_spoofing_tables.sql not found"

    def test_migration_creates_land_mask_table(self):
        sql = MIGRATION_PATH.read_text()
        assert "CREATE TABLE" in sql
        assert "land_mask" in sql

    def test_land_mask_has_required_columns(self):
        sql = MIGRATION_PATH.read_text()
        assert "SERIAL PRIMARY KEY" in sql
        assert "GEOGRAPHY" in sql.upper()
        assert "MULTIPOLYGON" in sql.upper()
        assert "4326" in sql
        assert "description" in sql

    def test_land_mask_has_gist_index(self):
        sql = MIGRATION_PATH.read_text()
        assert "idx_land_mask_geometry" in sql
        assert "GIST" in sql.upper()

    def test_migration_creates_gnss_interference_zones_table(self):
        sql = MIGRATION_PATH.read_text()
        assert "gnss_interference_zones" in sql

    def test_gnss_zones_has_required_columns(self):
        sql = MIGRATION_PATH.read_text()
        assert "BIGSERIAL PRIMARY KEY" in sql
        assert "detected_at" in sql
        assert "expires_at" in sql
        assert "affected_count" in sql
        assert "JSONB" in sql.upper()

    def test_gnss_zones_has_gist_index(self):
        sql = MIGRATION_PATH.read_text()
        assert "idx_gnss_zones_geometry" in sql

    def test_gnss_zones_has_expires_at_index(self):
        sql = MIGRATION_PATH.read_text()
        assert "idx_gnss_zones_expires_at" in sql

    def test_migration_uses_if_not_exists(self):
        sql = MIGRATION_PATH.read_text()
        assert sql.count("IF NOT EXISTS") >= 2, "Tables should use IF NOT EXISTS"
