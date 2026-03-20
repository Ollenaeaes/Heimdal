#!/usr/bin/env python3
"""Load EEZ and 12nm maritime boundaries from VLIZ shapefiles.

Loads two types of data:
  1. maritime_zones      — polygon zones for spatial containment queries
  2. maritime_boundaries — boundary lines for lightweight map display

Usage (local):
    python scripts/load_maritime_zones.py --database-url "postgresql://heimdal:heimdal_dev@localhost:5432/heimdal"

Usage (prod):
    python scripts/load_maritime_zones.py --database-url "postgresql://heimdal:PASSWORD@HOST:5432/heimdal"

Options:
    --eez-path       Path to EEZ polygon shapefile
    --eez-lines-path Path to EEZ boundary lines shapefile
    --12nm-path      Path to 12nm polygon shapefile
    --simplify       Simplification tolerance for polygons in degrees (default: 0.02 ≈ 2km)
    --lines-simplify Simplification tolerance for boundary lines in degrees (default: 0.005 ≈ 500m)
    --dry-run        Parse and validate without writing
    --database-url   PostgreSQL connection string (required)
    --clear          Clear existing data before loading
    --only           Load only 'eez', '12nm', or 'lines'
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger("load_maritime_zones")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EEZ_PATH = PROJECT_ROOT / "data" / "raw" / "World_EEZ_v12_20231025 3" / "eez_v12.shp"
DEFAULT_EEZ_LINES_PATH = PROJECT_ROOT / "data" / "raw" / "World_EEZ_v12_20231025 3" / "eez_boundaries_v12.shp"
DEFAULT_12NM_PATH = PROJECT_ROOT / "data" / "raw" / "World_12NM_v4_20231025" / "eez_12nm_v4.shp"


def read_shapefile(path: Path) -> list[dict]:
    """Read features from a shapefile using fiona."""
    try:
        import fiona
    except ImportError:
        logger.error("fiona is required: pip install fiona")
        sys.exit(1)

    features = []
    with fiona.open(str(path)) as src:
        for record in src:
            features.append({
                "properties": dict(record.get("properties", {})),
                "geometry": dict(record.get("geometry", {})),
            })
    return features


def polygon_to_wkt(geom: dict) -> str | None:
    """Convert a GeoJSON Polygon/MultiPolygon to WKT MULTIPOLYGON."""
    geom_type = geom.get("type", "")
    coords = geom.get("coordinates", [])

    if geom_type == "Polygon":
        rings = []
        for ring in coords:
            pts = ", ".join(f"{lon} {lat}" for lon, lat in ring)
            rings.append(f"({pts})")
        return f"MULTIPOLYGON(({', '.join(rings)}))"
    elif geom_type == "MultiPolygon":
        polygons = []
        for polygon in coords:
            rings = []
            for ring in polygon:
                pts = ", ".join(f"{lon} {lat}" for lon, lat in ring)
                rings.append(f"({pts})")
            polygons.append(f"({', '.join(rings)})")
        return f"MULTIPOLYGON({', '.join(polygons)})"
    else:
        return None


def linestring_to_wkt(geom: dict) -> str | None:
    """Convert a GeoJSON LineString/MultiLineString to WKT LINESTRING."""
    geom_type = geom.get("type", "")
    coords = geom.get("coordinates", [])

    if geom_type == "LineString":
        if len(coords) < 2:
            return None
        pts = ", ".join(f"{lon} {lat}" for lon, lat in coords)
        return f"LINESTRING({pts})"
    elif geom_type == "MultiLineString":
        # Take the longest line segment
        longest = max(coords, key=len) if coords else None
        if not longest or len(longest) < 2:
            return None
        pts = ", ".join(f"{lon} {lat}" for lon, lat in longest)
        return f"LINESTRING({pts})"
    else:
        return None


def extract_eez_fields(props: dict) -> dict:
    """Extract relevant fields from EEZ polygon shapefile."""
    return {
        "mrgid": props.get("MRGID"),
        "geoname": props.get("GEONAME"),
        "sovereign": props.get("SOVEREIGN1"),
        "iso_sov": props.get("ISO_TER1"),
        "territory": props.get("TERRITORY1"),
        "iso_ter": props.get("ISO_TER1"),
        "pol_type": props.get("POL_TYPE"),
        "area_km2": None,
        "metadata": json.dumps({
            k: str(v) for k, v in props.items()
            if v is not None and k not in (
                "MRGID", "GEONAME", "SOVEREIGN1", "ISO_TER1",
                "TERRITORY1", "POL_TYPE"
            )
        }),
    }


def extract_12nm_fields(props: dict) -> dict:
    """Extract relevant fields from 12nm polygon shapefile."""
    return {
        "mrgid": props.get("MRGID"),
        "geoname": props.get("GEONAME"),
        "sovereign": props.get("SOVEREIGN1"),
        "iso_sov": props.get("ISO_SOV1") or props.get("ISO_TER1"),
        "territory": props.get("TERRITORY1"),
        "iso_ter": props.get("ISO_TER1"),
        "pol_type": props.get("POL_TYPE"),
        "area_km2": props.get("AREA_KM2"),
        "metadata": json.dumps({
            k: str(v) for k, v in props.items()
            if v is not None and k not in (
                "MRGID", "GEONAME", "SOVEREIGN1", "ISO_SOV1",
                "ISO_TER1", "TERRITORY1", "POL_TYPE", "AREA_KM2"
            )
        }),
    }


def extract_boundary_fields(props: dict) -> dict:
    """Extract relevant fields from EEZ boundary lines shapefile."""
    return {
        "line_id": props.get("LINE_ID"),
        "line_name": props.get("LINE_NAME"),
        "line_type": props.get("LINE_TYPE"),
        "sovereign1": props.get("SOVEREIGN1"),
        "sovereign2": props.get("SOVEREIGN2"),
        "eez1": props.get("EEZ1"),
        "eez2": props.get("EEZ2"),
        "length_km": props.get("LENGTH_KM"),
        "metadata": json.dumps({
            k: str(v) for k, v in props.items()
            if v is not None and k not in (
                "LINE_ID", "LINE_NAME", "LINE_TYPE",
                "SOVEREIGN1", "SOVEREIGN2", "EEZ1", "EEZ2", "LENGTH_KM"
            )
        }),
    }


# ── Loading functions ──────────────────────────────────────────────


def load_zones(conn, features: list[dict], zone_type: str, simplify: float,
               clear: bool, dry_run: bool) -> int:
    """Load polygon zone features into maritime_zones."""
    cur = conn.cursor()
    try:
        if clear:
            cur.execute("DELETE FROM maritime_zones WHERE zone_type = %s", (zone_type,))
            logger.info("Cleared existing %s zones", zone_type)

        count = 0
        for i, feat in enumerate(features):
            wkt = feat["wkt"]
            fields = feat["fields"]

            if dry_run:
                logger.info("[DRY RUN] %s #%d: %s (%s)",
                            zone_type, i + 1, fields["geoname"], fields["iso_sov"])
                count += 1
                continue

            cur.execute(
                """
                INSERT INTO maritime_zones
                    (zone_type, mrgid, geoname, sovereign, iso_sov,
                     territory, iso_ter, pol_type, area_km2, geometry, metadata)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                     ST_SimplifyPreserveTopology(
                         ST_GeogFromText(%s)::geometry, %s
                     )::geography,
                     %s)
                """,
                (
                    zone_type,
                    fields["mrgid"], fields["geoname"], fields["sovereign"],
                    fields["iso_sov"], fields["territory"], fields["iso_ter"],
                    fields["pol_type"], fields["area_km2"],
                    wkt, simplify,
                    fields["metadata"],
                ),
            )
            count += 1
            if count % 25 == 0:
                logger.info("  Inserted %d/%d %s zones...", count, len(features), zone_type)

        if not dry_run:
            conn.commit()
        return count
    finally:
        cur.close()


def load_boundaries(conn, features: list[dict], boundary_type: str,
                    simplify: float, clear: bool, dry_run: bool) -> int:
    """Load boundary line features into maritime_boundaries."""
    cur = conn.cursor()
    try:
        if clear:
            cur.execute("DELETE FROM maritime_boundaries WHERE boundary_type = %s",
                        (boundary_type,))
            logger.info("Cleared existing %s boundaries", boundary_type)

        count = 0
        for i, feat in enumerate(features):
            wkt = feat["wkt"]
            fields = feat["fields"]

            if dry_run:
                logger.info("[DRY RUN] boundary #%d: %s (%s)",
                            i + 1, fields["line_name"], fields["line_type"])
                count += 1
                continue

            cur.execute(
                """
                INSERT INTO maritime_boundaries
                    (boundary_type, line_id, line_name, line_type,
                     sovereign1, sovereign2, eez1, eez2, length_km,
                     geometry, metadata)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                     ST_SimplifyPreserveTopology(
                         ST_GeogFromText(%s)::geometry, %s
                     )::geography,
                     %s)
                """,
                (
                    boundary_type,
                    fields["line_id"], fields["line_name"], fields["line_type"],
                    fields["sovereign1"], fields["sovereign2"],
                    fields["eez1"], fields["eez2"], fields["length_km"],
                    wkt, simplify,
                    fields["metadata"],
                ),
            )
            count += 1
            if count % 100 == 0:
                logger.info("  Inserted %d/%d %s boundaries...",
                            count, len(features), boundary_type)

        if not dry_run:
            conn.commit()
        return count
    finally:
        cur.close()


# ── Preparation ────────────────────────────────────────────────────


def prepare_polygon_features(path: Path, zone_type: str, extractor) -> list[dict]:
    """Read polygon shapefile and prepare features."""
    logger.info("Reading %s polygons from %s ...", zone_type, path.name)
    raw = read_shapefile(path)
    logger.info("  Parsed %d features", len(raw))

    prepared = []
    skipped = 0
    for feat in raw:
        wkt = polygon_to_wkt(feat["geometry"])
        if not wkt:
            skipped += 1
            continue
        fields = extractor(feat["properties"])
        prepared.append({"wkt": wkt, "fields": fields})

    if skipped:
        logger.info("  Skipped %d features with unsupported geometry", skipped)
    return prepared


def prepare_boundary_features(path: Path) -> list[dict]:
    """Read boundary lines shapefile and prepare features."""
    logger.info("Reading EEZ boundary lines from %s ...", path.name)
    raw = read_shapefile(path)
    logger.info("  Parsed %d features", len(raw))

    prepared = []
    skipped = 0
    for feat in raw:
        wkt = linestring_to_wkt(feat["geometry"])
        if not wkt:
            skipped += 1
            continue
        fields = extract_boundary_fields(feat["properties"])
        prepared.append({"wkt": wkt, "fields": fields})

    if skipped:
        logger.info("  Skipped %d features with unsupported geometry", skipped)
    return prepared


# ── Main ───────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load EEZ and 12nm maritime zones and boundaries into the database."
    )
    parser.add_argument("--eez-path", type=Path, default=DEFAULT_EEZ_PATH,
                        help="Path to EEZ polygon shapefile")
    parser.add_argument("--eez-lines-path", type=Path, default=DEFAULT_EEZ_LINES_PATH,
                        help="Path to EEZ boundary lines shapefile")
    parser.add_argument("--12nm-path", type=Path, default=DEFAULT_12NM_PATH,
                        dest="nm12_path", help="Path to 12nm polygon shapefile")
    parser.add_argument("--simplify", type=float, default=0.02,
                        help="Simplification tolerance for polygons (default: 0.02 ≈ 2km)")
    parser.add_argument("--lines-simplify", type=float, default=0.005,
                        help="Simplification tolerance for boundary lines (default: 0.005 ≈ 500m)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--database-url", type=str, required=True,
                        help="PostgreSQL connection URL")
    parser.add_argument("--clear", action="store_true",
                        help="Clear existing data before loading")
    parser.add_argument("--only", choices=["eez", "12nm", "lines"], default=None,
                        help="Load only one data type")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s: %(message)s",
                        datefmt="%H:%M:%S")

    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 is required: pip install psycopg2-binary")
        sys.exit(1)

    conn = psycopg2.connect(args.database_url)
    total = 0

    try:
        # --- EEZ polygons ---
        if args.only in (None, "eez"):
            if not args.eez_path.exists():
                logger.error("EEZ shapefile not found: %s", args.eez_path)
                sys.exit(1)
            feats = prepare_polygon_features(args.eez_path, "eez", extract_eez_fields)
            count = load_zones(conn, feats, "eez", args.simplify, args.clear, args.dry_run)
            logger.info("EEZ zones: loaded %d", count)
            total += count

        # --- 12nm polygons ---
        if args.only in (None, "12nm"):
            if not args.nm12_path.exists():
                logger.error("12nm shapefile not found: %s", args.nm12_path)
                sys.exit(1)
            feats = prepare_polygon_features(args.nm12_path, "12nm", extract_12nm_fields)
            count = load_zones(conn, feats, "12nm", args.simplify, args.clear, args.dry_run)
            logger.info("12nm zones: loaded %d", count)
            total += count

        # --- EEZ boundary lines ---
        if args.only in (None, "lines"):
            if not args.eez_lines_path.exists():
                logger.error("EEZ boundary lines shapefile not found: %s", args.eez_lines_path)
                sys.exit(1)
            feats = prepare_boundary_features(args.eez_lines_path)
            count = load_boundaries(conn, feats, "eez", args.lines_simplify,
                                    args.clear, args.dry_run)
            logger.info("EEZ boundaries: loaded %d", count)
            total += count

        logger.info("--- Done: %d total records loaded ---", total)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
