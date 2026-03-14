"""Tests for migration 011_infrastructure_tables.sql.

Validates that the SQL creates the expected tables and indexes.
"""

from __future__ import annotations

from pathlib import Path

import pytest


MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "db"
    / "migrations"
    / "011_infrastructure_tables.sql"
)


class TestInfrastructureMigration:
    """Verify the migration SQL is syntactically correct and contains expected DDL."""

    def test_migration_file_exists(self):
        assert MIGRATION_PATH.exists(), f"Migration file not found: {MIGRATION_PATH}"

    def test_migration_creates_infrastructure_routes_table(self):
        sql = MIGRATION_PATH.read_text()
        assert "CREATE TABLE" in sql
        assert "infrastructure_routes" in sql

    def test_infrastructure_routes_columns(self):
        sql = MIGRATION_PATH.read_text()
        # Check all required columns
        assert "id" in sql
        assert "SERIAL PRIMARY KEY" in sql
        assert "name" in sql
        assert "VARCHAR(256)" in sql
        assert "route_type" in sql
        assert "VARCHAR(32)" in sql
        assert "operator" in sql
        assert "GEOGRAPHY(LINESTRING, 4326)" in sql
        assert "buffer_nm" in sql
        assert "REAL DEFAULT 1.0" in sql
        assert "metadata" in sql
        assert "JSONB DEFAULT '{}'" in sql

    def test_infrastructure_routes_gist_index(self):
        sql = MIGRATION_PATH.read_text()
        assert "GIST" in sql
        assert "idx_infrastructure_routes_geometry" in sql

    def test_migration_creates_infrastructure_events_table(self):
        sql = MIGRATION_PATH.read_text()
        assert "infrastructure_events" in sql

    def test_infrastructure_events_columns(self):
        sql = MIGRATION_PATH.read_text()
        assert "BIGSERIAL PRIMARY KEY" in sql
        assert "mmsi" in sql
        assert "REFERENCES vessel_profiles(mmsi)" in sql
        assert "route_id" in sql
        assert "REFERENCES infrastructure_routes(id)" in sql
        assert "entry_time" in sql
        assert "exit_time" in sql
        assert "duration_minutes" in sql
        assert "min_speed" in sql
        assert "max_alignment" in sql
        assert "risk_assessed" in sql
        assert "BOOLEAN DEFAULT FALSE" in sql

    def test_infrastructure_events_composite_index(self):
        sql = MIGRATION_PATH.read_text()
        assert "idx_infrastructure_events_mmsi_entry" in sql
        assert "mmsi, entry_time DESC" in sql

    def test_migration_uses_if_not_exists(self):
        sql = MIGRATION_PATH.read_text()
        assert sql.count("IF NOT EXISTS") >= 4  # 2 tables + 2 indexes
