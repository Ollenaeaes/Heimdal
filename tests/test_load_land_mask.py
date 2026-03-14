"""Tests for scripts/load_land_mask.py."""

import json
from pathlib import Path

import pytest

from scripts.load_land_mask import (
    _geometry_to_wkt,
    _load_geojson,
    is_on_land_sql,
    load_features,
)


FIXTURE_PATH = Path(__file__).parent.parent / "data" / "land_mask" / "test_land.geojson"


class TestLoadGeoJSON:
    """Test GeoJSON loading."""

    def test_fixture_file_exists(self):
        assert FIXTURE_PATH.exists(), "Test GeoJSON fixture not found"

    def test_load_fixture_returns_features(self):
        features = _load_geojson(FIXTURE_PATH)
        assert len(features) >= 2, "Expected at least 2 features (Germany + France)"

    def test_features_have_geometry(self):
        features = _load_geojson(FIXTURE_PATH)
        for f in features:
            assert "geometry" in f
            assert f["geometry"]["type"] in ("Polygon", "MultiPolygon")

    def test_germany_covers_berlin(self):
        """Berlin is at 52.52, 13.405 — should be within the Germany polygon."""
        features = _load_geojson(FIXTURE_PATH)
        germany = None
        for f in features:
            desc = (f.get("properties") or {}).get("description", "")
            if "Germany" in desc or "Berlin" in desc:
                germany = f
                break
        assert germany is not None, "Could not find Germany feature"

        # Check Berlin coordinates are within bounding box
        coords = germany["geometry"]["coordinates"]
        if germany["geometry"]["type"] == "MultiPolygon":
            ring = coords[0][0]  # first polygon, outer ring
        else:
            ring = coords[0]

        lats = [p[1] for p in ring]
        lons = [p[0] for p in ring]
        assert min(lats) < 52.52 < max(lats), "Berlin lat not in range"
        assert min(lons) < 13.405 < max(lons), "Berlin lon not in range"

    def test_load_features_geojson(self):
        features = load_features(FIXTURE_PATH)
        assert len(features) >= 2

    def test_load_features_unsupported_format(self):
        with pytest.raises(ValueError, match="Unsupported"):
            load_features(Path("test.xyz"))


class TestGeometryToWKT:
    """Test WKT conversion."""

    def test_polygon_to_multipolygon_wkt(self):
        geom = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        }
        wkt = _geometry_to_wkt(geom)
        assert wkt.startswith("MULTIPOLYGON")
        assert "0 0" in wkt

    def test_multipolygon_wkt(self):
        geom = {
            "type": "MultiPolygon",
            "coordinates": [
                [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                [[[2, 2], [3, 2], [3, 3], [2, 2]]],
            ],
        }
        wkt = _geometry_to_wkt(geom)
        assert wkt.startswith("MULTIPOLYGON")
        assert "2 2" in wkt

    def test_unsupported_geometry_type(self):
        with pytest.raises(ValueError, match="Expected Polygon or MultiPolygon"):
            _geometry_to_wkt({"type": "Point", "coordinates": [0, 0]})


class TestIsOnLandSQL:
    """Test SQL helper."""

    def test_returns_sql_string(self):
        sql = is_on_land_sql()
        assert "SELECT EXISTS" in sql
        assert "land_mask" in sql
        assert "ST_Intersects" in sql
