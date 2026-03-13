"""Tests for extended STS hotspot coverage (Story 5, Spec 18).

Validates that config.yaml and the migration file contain all 12 STS
hotspot AOIs (6 original + 6 new) with correct structure and coordinates.
"""

import re
from pathlib import Path

import yaml
import pytest

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "config.yaml"
MIGRATION_004 = ROOT / "db" / "migrations" / "004_seed_data.sql"
MIGRATION_008 = ROOT / "db" / "migrations" / "008_new_sts_zones.sql"

ORIGINAL_AOI_NAMES = [
    "Kalamata, Greece",
    "Laconian Gulf, Greece",
    "Ceuta, Spain",
    "Lome, Togo",
    "South of Malta",
    "UAE/Fujairah",
]

NEW_AOI_NAMES = [
    "South China Sea",
    "Gulf of Oman",
    "Singapore Strait",
    "Alboran Sea",
    "Baltic/Primorsk",
    "South of Crete",
]

NEW_ZONE_NAMES = [
    "South China Sea STS",
    "Gulf of Oman STS",
    "Singapore Strait STS",
    "Alboran Sea STS",
    "Baltic/Primorsk STS",
    "South of Crete STS",
]


@pytest.fixture(scope="module")
def config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def migration_008_sql():
    return MIGRATION_008.read_text()


# ── Config AOI tests ─────────────────────────────────────────────────


class TestConfigAOIs:
    def test_config_has_12_aois(self, config):
        aois = config["gfw"]["aois"]
        assert len(aois) == 12, f"Expected 12 AOIs, got {len(aois)}"

    def test_original_aois_present(self, config):
        aoi_names = [a["name"] for a in config["gfw"]["aois"]]
        for name in ORIGINAL_AOI_NAMES:
            assert name in aoi_names, f"Original AOI '{name}' missing from config"

    def test_new_aois_present(self, config):
        aoi_names = [a["name"] for a in config["gfw"]["aois"]]
        for name in NEW_AOI_NAMES:
            assert name in aoi_names, f"New AOI '{name}' missing from config"

    def test_all_aois_have_valid_coordinates(self, config):
        for aoi in config["gfw"]["aois"]:
            coords = aoi["coordinates"]
            assert len(coords) == 5, (
                f"AOI '{aoi['name']}' should have 5 coordinate pairs "
                f"(closed ring), got {len(coords)}"
            )
            # First and last coordinate must be equal (closed polygon)
            assert coords[0] == coords[-1], (
                f"AOI '{aoi['name']}' polygon is not closed: "
                f"first={coords[0]}, last={coords[-1]}"
            )
            # Each coordinate is [lon, lat]
            for coord in coords:
                assert len(coord) == 2, (
                    f"AOI '{aoi['name']}' has invalid coordinate: {coord}"
                )
                lon, lat = coord
                assert -180 <= lon <= 180, (
                    f"AOI '{aoi['name']}' longitude out of range: {lon}"
                )
                assert -90 <= lat <= 90, (
                    f"AOI '{aoi['name']}' latitude out of range: {lat}"
                )


# ── Migration file tests ─────────────────────────────────────────────


class TestMigration008:
    def test_migration_file_exists(self):
        assert MIGRATION_008.exists(), "Migration 008_new_sts_zones.sql not found"

    def test_all_new_zones_present(self, migration_008_sql):
        for zone_name in NEW_ZONE_NAMES:
            assert zone_name in migration_008_sql, (
                f"Zone '{zone_name}' not found in migration 008"
            )

    def test_all_zones_are_sts_type(self, migration_008_sql):
        # Every INSERT should use 'sts_zone' as zone_type
        inserts = re.findall(
            r"INSERT INTO zones.*?ON CONFLICT DO NOTHING;",
            migration_008_sql,
            re.DOTALL,
        )
        assert len(inserts) == 6, f"Expected 6 INSERT statements, got {len(inserts)}"
        for insert in inserts:
            assert "'sts_zone'" in insert, (
                f"INSERT missing 'sts_zone' type:\n{insert[:100]}..."
            )

    def test_all_zones_have_valid_polygons(self, migration_008_sql):
        polygons = re.findall(r"POLYGON\(\(([^)]+)\)\)", migration_008_sql)
        assert len(polygons) == 6, f"Expected 6 POLYGONs, got {len(polygons)}"
        for poly in polygons:
            points = poly.split(", ")
            assert len(points) == 5, (
                f"Polygon should have 5 points (closed ring), got {len(points)}: {poly}"
            )
            # First and last point must match (closed ring)
            assert points[0] == points[-1], (
                f"Polygon not closed: first={points[0]}, last={points[-1]}"
            )

    def test_uses_on_conflict_do_nothing(self, migration_008_sql):
        inserts = migration_008_sql.count("ON CONFLICT DO NOTHING")
        assert inserts == 6, (
            f"Expected 6 ON CONFLICT DO NOTHING clauses, got {inserts}"
        )

    def test_uses_geography_type(self, migration_008_sql):
        """Migration should use ST_GeogFromText to match existing pattern."""
        geog_count = migration_008_sql.count("ST_GeogFromText")
        assert geog_count == 6, (
            f"Expected 6 ST_GeogFromText calls, got {geog_count}"
        )
