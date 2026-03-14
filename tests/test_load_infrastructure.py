"""Tests for the infrastructure data loading script.

Validates GeoJSON parsing, validation logic, and WKT generation
without requiring a live database.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import after path setup
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.load_infrastructure import (
    VALID_ROUTE_TYPES,
    _coords_to_linestring_wkt,
    _read_geojson,
    load_features,
)


SAMPLE_GEOJSON = Path(__file__).resolve().parent.parent / "data" / "infrastructure" / "sample_cables.geojson"


class TestSampleFixture:
    """Verify the sample GeoJSON fixture is valid."""

    def test_sample_file_exists(self):
        assert SAMPLE_GEOJSON.exists()

    def test_sample_is_valid_json(self):
        data = json.loads(SAMPLE_GEOJSON.read_text())
        assert data["type"] == "FeatureCollection"

    def test_sample_has_features(self):
        data = json.loads(SAMPLE_GEOJSON.read_text())
        assert len(data["features"]) >= 3

    def test_sample_features_have_required_properties(self):
        data = json.loads(SAMPLE_GEOJSON.read_text())
        for feature in data["features"]:
            props = feature["properties"]
            assert "name" in props, f"Feature missing 'name': {props}"
            assert "route_type" in props, f"Feature missing 'route_type': {props}"
            assert props["route_type"] in VALID_ROUTE_TYPES, (
                f"Invalid route_type: {props['route_type']}"
            )

    def test_sample_features_are_linestrings(self):
        data = json.loads(SAMPLE_GEOJSON.read_text())
        for feature in data["features"]:
            assert feature["geometry"]["type"] == "LineString"
            assert len(feature["geometry"]["coordinates"]) >= 2

    def test_sample_has_multiple_route_types(self):
        data = json.loads(SAMPLE_GEOJSON.read_text())
        types = {f["properties"]["route_type"] for f in data["features"]}
        assert len(types) >= 2, f"Only found types: {types}"


class TestReadGeoJSON:
    """Test GeoJSON file parsing."""

    def test_read_feature_collection(self):
        features = _read_geojson(SAMPLE_GEOJSON)
        assert len(features) >= 3

    def test_read_single_feature(self, tmp_path):
        single = {
            "type": "Feature",
            "properties": {"name": "Test Cable", "route_type": "telecom_cable"},
            "geometry": {
                "type": "LineString",
                "coordinates": [[10.0, 55.0], [11.0, 55.5]],
            },
        }
        p = tmp_path / "single.geojson"
        p.write_text(json.dumps(single))
        features = _read_geojson(p)
        assert len(features) == 1
        assert features[0]["properties"]["name"] == "Test Cable"

    def test_read_unsupported_type_raises(self, tmp_path):
        bad = {"type": "Point", "coordinates": [10, 55]}
        p = tmp_path / "bad.geojson"
        p.write_text(json.dumps(bad))
        with pytest.raises(ValueError, match="Unsupported GeoJSON type"):
            _read_geojson(p)


class TestCoordsToWKT:
    """Test WKT generation from coordinates."""

    def test_simple_linestring(self):
        coords = [[10.0, 55.0], [11.0, 55.5], [12.0, 56.0]]
        wkt = _coords_to_linestring_wkt(coords)
        assert wkt == "LINESTRING(10.0 55.0, 11.0 55.5, 12.0 56.0)"

    def test_two_point_linestring(self):
        coords = [[1.5, 2.5], [3.5, 4.5]]
        wkt = _coords_to_linestring_wkt(coords)
        assert wkt == "LINESTRING(1.5 2.5, 3.5 4.5)"


class TestLoadFeaturesValidation:
    """Test feature validation without DB writes."""

    @pytest.mark.asyncio
    async def test_skip_feature_without_name(self):
        features = [
            {
                "properties": {"route_type": "telecom_cable"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[10, 55], [11, 55.5]],
                },
            }
        ]
        # dry_run so no DB needed
        counts = await load_features(features, dry_run=True)
        assert counts["skipped"] == 1

    @pytest.mark.asyncio
    async def test_skip_invalid_route_type(self):
        features = [
            {
                "properties": {"name": "Test", "route_type": "water_pipe"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[10, 55], [11, 55.5]],
                },
            }
        ]
        counts = await load_features(features, dry_run=True)
        assert counts["skipped"] == 1

    @pytest.mark.asyncio
    async def test_skip_non_linestring_geometry(self):
        features = [
            {
                "properties": {"name": "Test", "route_type": "telecom_cable"},
                "geometry": {
                    "type": "Point",
                    "coordinates": [10, 55],
                },
            }
        ]
        counts = await load_features(features, dry_run=True)
        assert counts["skipped"] == 1

    @pytest.mark.asyncio
    async def test_skip_too_few_coordinates(self):
        features = [
            {
                "properties": {"name": "Test", "route_type": "telecom_cable"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[10, 55]],
                },
            }
        ]
        counts = await load_features(features, dry_run=True)
        assert counts["skipped"] == 1

    @pytest.mark.asyncio
    async def test_dry_run_counts_valid_features(self):
        features = [
            {
                "properties": {"name": "Cable A", "route_type": "telecom_cable"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[10, 55], [11, 55.5]],
                },
            },
            {
                "properties": {"name": "Pipe B", "route_type": "gas_pipeline"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[20, 60], [21, 60.5]],
                },
            },
        ]
        counts = await load_features(features, dry_run=True)
        assert counts["telecom_cable"] == 1
        assert counts["gas_pipeline"] == 1
        assert counts.get("skipped", 0) == 0

    @pytest.mark.asyncio
    async def test_dry_run_sample_fixture(self):
        features = _read_geojson(SAMPLE_GEOJSON)
        counts = await load_features(features, dry_run=True)
        total = sum(c for k, c in counts.items() if k != "skipped")
        assert total == len(features)
