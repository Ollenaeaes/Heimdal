#!/usr/bin/env python3
"""Load infrastructure route data (cables, pipelines) from GeoJSON or Shapefile.

Usage:
    # From sample GeoJSON (has route_type in properties)
    python scripts/load_infrastructure.py data/infrastructure/sample_cables.geojson

    # From TeleGeography cable GeoJSON (override route_type)
    python scripts/load_infrastructure.py --input data/infrastructure/cable-geo.json --type telecom_cable

    # From EMODnet pipeline shapefile
    python scripts/load_infrastructure.py --input data/infrastructure/pipelinesLine.shp --type gas_pipeline

    # From EMODnet cable shapefile
    python scripts/load_infrastructure.py --input data/infrastructure/pcablesnveLine.shp --type power_cable

Supports GeoJSON (.geojson/.json) natively.  Shapefile (.shp) requires
``fiona`` to be installed.

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

VALID_ROUTE_TYPES = {"telecom_cable", "power_cable", "gas_pipeline", "oil_pipeline", "pipeline"}


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


def _extract_name(props: dict, index: int) -> str | None:
    """Extract a name from feature properties, trying common field names."""
    for key in ("name", "NAME", "Name", "navn", "NAVN", "label", "LABEL",
                "id", "ID", "lokalid", "feature_id"):
        val = props.get(key)
        if val and str(val).strip():
            return str(val).strip()
    # Build a name from from_loc/to_loc if available
    from_loc = props.get("from_loc") or props.get("from")
    to_loc = props.get("to_loc") or props.get("to")
    if from_loc and to_loc:
        return f"{from_loc} - {to_loc}"
    # Fallback: generate a name from the file
    return None


def _normalize_features(features: list[dict], type_override: str | None, source_name: str) -> list[dict]:
    """Normalize features: set route_type, handle MultiLineString, generate names."""
    normalized = []
    unnamed_counter = 0

    for feature in features:
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})
        geom_type = geom.get("type", "")
        coords = geom.get("coordinates", [])

        # Determine route_type
        route_type = type_override or props.get("route_type")
        if not route_type:
            # Try to infer from medium field (EMODnet pipelines)
            medium = props.get("medium", "")
            if medium:
                medium_lower = medium.lower()
                if "gas" in medium_lower:
                    route_type = "gas_pipeline"
                elif "oil" in medium_lower:
                    route_type = "oil_pipeline"
                else:
                    route_type = "pipeline"
            else:
                route_type = "telecom_cable"  # default

        # Normalize pipeline -> gas_pipeline
        if route_type == "pipeline":
            route_type = "gas_pipeline"

        # Handle MultiLineString by splitting into individual LineStrings
        if geom_type == "MultiLineString":
            for i, line_coords in enumerate(coords):
                if len(line_coords) < 2:
                    continue
                name = _extract_name(props, unnamed_counter)
                if not name:
                    unnamed_counter += 1
                    name = f"{source_name}-{unnamed_counter}"
                # For multi-part geometries, append part index
                feat_name = f"{name}" if len(coords) == 1 else f"{name} (part {i+1})"
                normalized.append({
                    "name": feat_name,
                    "route_type": route_type,
                    "operator": props.get("operator") or props.get("eier"),
                    "buffer_nm": props.get("buffer_nm", 1.0),
                    "metadata": {k: str(v) for k, v in props.items()
                                 if k not in ("name", "route_type", "operator", "buffer_nm")
                                 and v is not None},
                    "coordinates": line_coords,
                })
        elif geom_type == "LineString":
            if len(coords) < 2:
                continue
            name = _extract_name(props, unnamed_counter)
            if not name:
                unnamed_counter += 1
                name = f"{source_name}-{unnamed_counter}"
            normalized.append({
                "name": name,
                "route_type": route_type,
                "operator": props.get("operator") or props.get("eier"),
                "buffer_nm": props.get("buffer_nm", 1.0),
                "metadata": {k: str(v) for k, v in props.items()
                             if k not in ("name", "route_type", "operator", "buffer_nm")
                             and v is not None},
                "coordinates": coords,
            })
        else:
            logger.warning("Skipping unsupported geometry type: %s", geom_type)

    return normalized


async def load_normalized_features(features: list[dict], dry_run: bool = False) -> Counter:
    """Insert or update infrastructure routes from normalized features."""
    counts: Counter = Counter()

    if dry_run:
        for feat in features:
            logger.info("[DRY RUN] Would upsert: %s (%s)", feat["name"], feat["route_type"])
            counts[feat["route_type"]] += 1
        return counts

    session_factory = get_session()
    async with session_factory() as session:
        for feat in features:
            wkt = _coords_to_linestring_wkt(feat["coordinates"])

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
                    "name": feat["name"],
                    "route_type": feat["route_type"],
                    "operator": feat["operator"],
                    "wkt": wkt,
                    "buffer_nm": feat["buffer_nm"],
                    "metadata": json.dumps(feat["metadata"]),
                },
            )
            row = result.first()
            if row:
                counts[feat["route_type"]] += 1
                continue

            # Insert new
            result = await session.execute(
                text("""
                    INSERT INTO infrastructure_routes (name, route_type, operator, geometry, buffer_nm, metadata)
                    VALUES (:name, :route_type, :operator, ST_GeogFromText(:wkt), :buffer_nm, :metadata)
                    RETURNING id
                """),
                {
                    "name": feat["name"],
                    "route_type": feat["route_type"],
                    "operator": feat["operator"],
                    "wkt": wkt,
                    "buffer_nm": feat["buffer_nm"],
                    "metadata": json.dumps(feat["metadata"]),
                },
            )
            counts[feat["route_type"]] += 1

        await session.commit()

    return counts


# Keep old interface for backward compat with tests
async def load_features(features: list[dict], dry_run: bool = False) -> Counter:
    """Insert or update infrastructure routes from parsed GeoJSON features."""
    normalized = _normalize_features(features, None, "unknown")
    return await load_normalized_features(normalized, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load infrastructure routes into the database."
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        type=Path,
        help="Path to GeoJSON (.geojson/.json) or Shapefile (.shp)",
    )
    parser.add_argument(
        "--input",
        type=Path,
        dest="input_flag",
        help="Path to GeoJSON or Shapefile (alternative to positional arg)",
    )
    parser.add_argument(
        "--type",
        dest="route_type",
        choices=sorted(VALID_ROUTE_TYPES),
        help="Override route_type for all features in the file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate without writing to the database",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    path: Path = args.input_flag or args.input_file
    if not path:
        parser.error("Provide an input file as positional arg or via --input")
    if not path.exists():
        logger.error("File not found: %s", path)
        sys.exit(1)

    suffix = path.suffix.lower()
    if suffix in (".geojson", ".json"):
        raw_features = _read_geojson(path)
    elif suffix == ".shp":
        raw_features = _read_shapefile(path)
    else:
        logger.error("Unsupported file type: %s (expected .geojson, .json, or .shp)", suffix)
        sys.exit(1)

    logger.info("Parsed %d raw features from %s", len(raw_features), path.name)

    source_name = path.stem
    normalized = _normalize_features(raw_features, args.route_type, source_name)
    logger.info("Normalized to %d LineString features", len(normalized))

    counts = asyncio.run(load_normalized_features(normalized, dry_run=args.dry_run))

    logger.info("--- Summary ---")
    for route_type, count in sorted(counts.items()):
        logger.info("  %s: %d", route_type, count)
    total = sum(c for k, c in counts.items() if k != "skipped")
    skipped = counts.get("skipped", 0)
    logger.info("  Total loaded: %d, Skipped: %d", total, skipped)


if __name__ == "__main__":
    main()
