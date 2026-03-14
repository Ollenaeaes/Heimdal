"""Load coastline/land polygon data into the land_mask table.

Supports GeoJSON (.geojson, .json) and Shapefile (.shp) input formats.

Usage:
    python scripts/load_land_mask.py data/land_mask/test_land.geojson
    python scripts/load_land_mask.py /path/to/coastline.shp
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GeoJSON helpers
# ---------------------------------------------------------------------------

def _load_geojson(path: Path) -> list[dict[str, Any]]:
    """Load features from a GeoJSON file."""
    with open(path) as f:
        data = json.load(f)

    if data.get("type") == "FeatureCollection":
        return data.get("features", [])
    elif data.get("type") == "Feature":
        return [data]
    else:
        raise ValueError(f"Unsupported GeoJSON type: {data.get('type')}")


def _load_shapefile(path: Path) -> list[dict[str, Any]]:
    """Load features from a shapefile using fiona (optional dependency)."""
    try:
        import fiona
        from shapely.geometry import mapping, shape
    except ImportError:
        raise ImportError(
            "Shapefile support requires 'fiona' and 'shapely'. "
            "Install with: pip install fiona shapely"
        )

    features = []
    with fiona.open(str(path)) as src:
        for record in src:
            geom = shape(record["geometry"])
            # Convert to MultiPolygon if needed
            if geom.geom_type == "Polygon":
                from shapely.geometry import MultiPolygon
                geom = MultiPolygon([geom])
            elif geom.geom_type != "MultiPolygon":
                logger.warning("Skipping non-polygon geometry: %s", geom.geom_type)
                continue

            features.append({
                "type": "Feature",
                "properties": dict(record.get("properties", {})),
                "geometry": mapping(geom),
            })
    return features


def load_features(path: Path) -> list[dict[str, Any]]:
    """Load features from a GeoJSON or Shapefile."""
    suffix = path.suffix.lower()
    if suffix in (".geojson", ".json"):
        return _load_geojson(path)
    elif suffix == ".shp":
        return _load_shapefile(path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Use .geojson, .json, or .shp")


def _geometry_to_wkt(geometry: dict[str, Any]) -> str:
    """Convert a GeoJSON geometry dict to WKT MULTIPOLYGON string."""
    geom_type = geometry.get("type", "")
    coords = geometry.get("coordinates", [])

    if geom_type == "Polygon":
        coords = [coords]
    elif geom_type != "MultiPolygon":
        raise ValueError(f"Expected Polygon or MultiPolygon, got {geom_type}")

    polygon_strs = []
    for polygon in coords:
        ring_strs = []
        for ring in polygon:
            points = ", ".join(f"{x} {y}" for x, y in ring)
            ring_strs.append(f"({points})")
        polygon_strs.append(f"({', '.join(ring_strs)})")

    return f"MULTIPOLYGON({', '.join(polygon_strs)})"


# ---------------------------------------------------------------------------
# Land/sea check helper
# ---------------------------------------------------------------------------

def is_on_land_sql() -> str:
    """Return a SQL fragment that checks if a point is on land.

    Usage with sqlalchemy.text():
        text(f'''
            SELECT EXISTS(
                SELECT 1 FROM land_mask
                WHERE ST_Intersects(
                    geometry,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                )
                AND NOT ST_DWithin(
                    geometry,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    -100  -- negative = exclude 100m coastal buffer
                )
            )
        ''')

    Simplified version — the caller should use ST_Intersects with a buffer
    exclusion for coastline tolerance.
    """
    return """
        SELECT EXISTS(
            SELECT 1 FROM land_mask
            WHERE ST_Intersects(
                geometry,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
            )
        )
    """


# ---------------------------------------------------------------------------
# DB insertion
# ---------------------------------------------------------------------------

async def insert_features(features: list[dict[str, Any]]) -> int:
    """Insert land mask features into the database. Returns count inserted."""
    from sqlalchemy import text
    from shared.db import get_session

    session_factory = get_session()
    inserted = 0

    async with session_factory() as session:
        # Clear existing data
        await session.execute(text("DELETE FROM land_mask"))

        for feature in features:
            geom = feature.get("geometry")
            if not geom:
                continue

            description = (feature.get("properties") or {}).get("description")
            wkt = _geometry_to_wkt(geom)

            await session.execute(
                text("""
                    INSERT INTO land_mask (geometry, description)
                    VALUES (
                        ST_GeogFromText(:wkt),
                        :description
                    )
                """),
                {"wkt": wkt, "description": description},
            )
            inserted += 1

        await session.commit()

    logger.info("Inserted %d land mask polygons", inserted)
    return inserted


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Load land mask data into the database")
    parser.add_argument("input_file", nargs="?", type=Path, help="GeoJSON or Shapefile path")
    parser.add_argument("--input", type=Path, dest="input_flag", help="GeoJSON or Shapefile path (alternative to positional)")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't insert")
    args = parser.parse_args()
    args.input_file = args.input_flag or args.input_file
    if not args.input_file:
        parser.error("Provide an input file as positional arg or via --input")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not args.input_file.exists():
        logger.error("File not found: %s", args.input_file)
        sys.exit(1)

    features = load_features(args.input_file)
    logger.info("Loaded %d features from %s", len(features), args.input_file)

    if args.dry_run:
        for f in features:
            desc = (f.get("properties") or {}).get("description", "N/A")
            logger.info("  Feature: %s", desc)
        return

    import asyncio
    count = asyncio.run(insert_features(features))
    logger.info("Done. Inserted %d polygons.", count)


if __name__ == "__main__":
    main()
