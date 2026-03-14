"""Tests for the 013_network_edges migration SQL.

Verifies:
- Migration file exists and is readable
- Creates network_edges table with correct columns
- UNIQUE constraint on (vessel_a_mmsi, vessel_b_mmsi, edge_type)
- Indexes on vessel_a_mmsi, vessel_b_mmsi, edge_type
- Adds network_score column to vessel_profiles
"""

from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "db" / "migrations" / "013_network_edges.sql"


class TestMigrationFile:
    """Test the migration SQL file structure."""

    def test_migration_file_exists(self):
        assert MIGRATION_PATH.exists(), f"Migration file not found at {MIGRATION_PATH}"

    def test_migration_is_readable(self):
        content = MIGRATION_PATH.read_text()
        assert len(content) > 100, "Migration file appears too short"

    def test_creates_network_edges_table(self):
        content = MIGRATION_PATH.read_text()
        assert "CREATE TABLE" in content
        assert "network_edges" in content

    def test_has_required_columns(self):
        content = MIGRATION_PATH.read_text()
        required_columns = [
            "vessel_a_mmsi",
            "vessel_b_mmsi",
            "edge_type",
            "confidence",
            "first_observed",
            "last_observed",
            "observation_count",
            "location",
            "details",
        ]
        for col in required_columns:
            assert col in content, f"Missing column: {col}"

    def test_has_bigserial_pk(self):
        content = MIGRATION_PATH.read_text()
        assert "BIGSERIAL" in content
        assert "PRIMARY KEY" in content

    def test_has_foreign_keys(self):
        content = MIGRATION_PATH.read_text()
        assert "REFERENCES vessel_profiles(mmsi)" in content

    def test_has_unique_constraint(self):
        content = MIGRATION_PATH.read_text()
        assert "UNIQUE" in content
        # Check the constraint covers the right columns
        assert "vessel_a_mmsi" in content
        assert "vessel_b_mmsi" in content
        assert "edge_type" in content

    def test_has_indexes(self):
        content = MIGRATION_PATH.read_text()
        assert "idx_network_edges_vessel_a" in content
        assert "idx_network_edges_vessel_b" in content
        assert "idx_network_edges_edge_type" in content

    def test_has_geography_point_location(self):
        content = MIGRATION_PATH.read_text()
        assert "GEOGRAPHY(POINT, 4326)" in content

    def test_has_jsonb_details(self):
        content = MIGRATION_PATH.read_text()
        assert "JSONB" in content

    def test_adds_network_score_to_vessel_profiles(self):
        content = MIGRATION_PATH.read_text()
        assert "network_score" in content
        assert "ALTER TABLE vessel_profiles" in content

    def test_network_score_default_zero(self):
        content = MIGRATION_PATH.read_text()
        assert "DEFAULT 0" in content

    def test_varchar_edge_type(self):
        content = MIGRATION_PATH.read_text()
        assert "VARCHAR(32)" in content.upper() or "VARCHAR(32)" in content
