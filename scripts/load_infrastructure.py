#!/usr/bin/env python3
"""Load infrastructure route data (cables, pipelines) from GeoJSON or Shapefile.

Usage:
    python scripts/load_infrastructure.py data/infrastructure/sample_cables.geojson

Supports GeoJSON (.geojson/.json) natively.  Shapefile (.shp) requires
``fiona`` or ``geopandas`` to be installed.

Routes are upserted based on (name, route_type).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio

from sqlalchemy import text

from shared.config import settings  # noqa: E402 — force settings init
from shared.db.connection import get_engine, get_session

logger = logging.getLogger("load_infrastructure")

VALID_ROUTE_TYPES = {"telecom_cable", "power_cable", "gas_pipeline", "oil_pipeline"}


def _read_geojson(path: Path) -> list[dict]:
    """Read features from a GeoJSON file."""
    with open(path) as f:
        data = json.load(f)

    if data.get("type") == "FeatureCollection":
        return data.get("features", [])
    elif data.get("type") == "Feature":
        return [data]
    else:
        raise ValueError(f"Unsupported GeoJSON type: {data.get('type')}")


def _read_shapefile(path: Path) -> list[dict]:
    """Read features from a Shapefile using fiona."""
    try:
        import fiona
    except ImportError:
        raise ImportError(
            "fiona is required to read shapefiles. "
            "Install with: pip install fiona"
        )

    features = []
    with fiona.open(str(path)) as src:
        for record in src:
            features.append({
                "type": "Feature",
                "properties": dict(record.get("properties", {})),
                "geometry": dict(record.get("geometry", {})),
            })
    return features


def _coords_to_linestring_wkt(coordinates: list[list[float]]) -> str:
    """Convert GeoJSON coordinate array to WKT LINESTRING."""
    parts = [f"{lon} {lat}" for lon, lat in coordinates]
    return f"LINESTRING({', '.join(parts)})"


async def load_features(features: list[dict], dry_run: bool = False) -> Counter:
    """Insert or update infrastructure routes from parsed GeoJSON features."""
    counts: Counter = Counter()

    session_factory = get_session()
    async with session_factory() as session:
        for feature in features:
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})

            name = props.get("name")
            route_type = props.get("route_type")
            operator = props.get("operator")
            buffer_nm = props.get("buffer_nm", 1.0)
            metadata = {
                k: v for k, v in props.items()
                if k not in ("name", "route_type", "operator", "buffer_nm")
            }

            if not name:
                logger.warning("Skipping feature without 'name' property")
                counts["skipped"] += 1
                continue

            if route_type not in VALID_ROUTE_TYPES:
                logger.warning(
                    "Skipping '%s': invalid route_type '%s' (expected one of %s)",
                    name, route_type, VALID_ROUTE_TYPES,
                )
                counts["skipped"] += 1
                continue

            if geom.get("type") != "LineString":
                logger.warning(
                    "Skipping '%s': geometry type '%s' is not LineString",
                    name, geom.get("type"),
                )
                counts["skipped"] += 1
                continue

            coords = geom.get("coordinates", [])
            if len(coords) < 2:
                logger.warning("Skipping '%s': fewer than 2 coordinates", name)
                counts["skipped"] += 1
                continue

            wkt = _coords_to_linestring_wkt(coords)

            if dry_run:
                logger.info("[DRY RUN] Would upsert: %s (%s)", name, route_type)
                counts[route_type] += 1
                continue

            # Upsert: try update first, then insert
            result = await session.execute(
                text("""
                    UPDATE infrastructure_routes
                    SET operator = :operator,
                        geometry = ST_GeogFromText(:wkt),
                        buffer_nm = :buffer_nm,
                        metadata = :metadata
                    WHERE name = :name AND route_type = :route_type
                    RETURNING id
                """),
                {
                    "name": name,
                    "route_type": route_type,
                    "operator": operator,
                    "wkt": wkt,
                    "buffer_nm": buffer_nm,
                    "metadata": json.dumps(metadata),
                },
            )
            row = result.first()
            if row:
                logger.info("Updated route: %s (%s) [id=%d]", name, route_type, row[0])
                counts[route_type] += 1
                continue

            # Insert new
            result = await session.execute(
                text("""
                    INSERT INTO infrastructure_routes (name, route_type, operator, geometry, buffer_nm, metadata)
                    VALUES (:name, :route_type, :operator, ST_GeogFromText(:wkt), :buffer_nm, :metadata)
                    RETURNING id
                """),
                {
                    "name": name,
                    "route_type": route_type,
                    "operator": operator,
                    "wkt": wkt,
                    "buffer_nm": buffer_nm,
                    "metadata": json.dumps(metadata),
                },
            )
            row = result.first()
            logger.info("Inserted route: %s (%s) [id=%d]", name, route_type, row[0])
            counts[route_type] += 1

        await session.commit()

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load infrastructure routes into the database."
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Path to GeoJSON (.geojson/.json) or Shapefile (.shp)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate without writing to the database",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    path: Path = args.input_file
    if not path.exists():
        logger.error("File not found: %s", path)
        sys.exit(1)

    suffix = path.suffix.lower()
    if suffix in (".geojson", ".json"):
        features = _read_geojson(path)
    elif suffix == ".shp":
        features = _read_shapefile(path)
    else:
        logger.error("Unsupported file type: %s (expected .geojson, .json, or .shp)", suffix)
        sys.exit(1)

    logger.info("Parsed %d features from %s", len(features), path.name)

    counts = asyncio.run(load_features(features, dry_run=args.dry_run))

    logger.info("--- Summary ---")
    for route_type, count in sorted(counts.items()):
        logger.info("  %s: %d", route_type, count)
    total = sum(c for k, c in counts.items() if k != "skipped")
    skipped = counts.get("skipped", 0)
    logger.info("  Total loaded: %d, Skipped: %d", total, skipped)


if __name__ == "__main__":
    main()
