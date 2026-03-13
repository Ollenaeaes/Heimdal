#!/usr/bin/env python3
"""Import GFW SAR vessel detection CSVs into the sar_detections table.

Usage:
    python scripts/import_sar_csv.py [--data-dir data/gfw-sar] [--batch-size 5000]

Reads all CSV files from the data directory and bulk-inserts them into
the database. Uses COPY-style batch inserts for performance (~1.5M rows).
Skips rows that conflict on gfw_detection_id (idempotent).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import math
import os
import sys
from pathlib import Path

import asyncio

# Add project root to path so shared/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from shared.db.connection import get_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("import_sar_csv")

# Column mapping: CSV header → DB column
# CSV: scene_id, timestamp, lat, lon, presence_score, length_m, mmsi,
#      matching_score, fishing_score, matched_category
# Use a subquery to only set matched_mmsi when the MMSI exists in vessel_profiles
# (the FK constraint would reject unknown MMSIs otherwise).
UPSERT_SQL = text("""
    INSERT INTO sar_detections (
        gfw_detection_id, detection_time, position,
        length_m, confidence, is_dark,
        matched_mmsi, matched_category,
        matching_score, fishing_score, source
    ) VALUES (
        :gfw_detection_id, :detection_time,
        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
        :length_m, :confidence, :is_dark,
        (SELECT mmsi FROM vessel_profiles WHERE mmsi = :matched_mmsi),
        :matched_category,
        :matching_score, :fishing_score, 'gfw-csv'
    )
    ON CONFLICT (gfw_detection_id) DO UPDATE SET
        detection_time = EXCLUDED.detection_time,
        position = EXCLUDED.position,
        length_m = EXCLUDED.length_m,
        confidence = EXCLUDED.confidence,
        is_dark = EXCLUDED.is_dark,
        matched_mmsi = EXCLUDED.matched_mmsi,
        matched_category = EXCLUDED.matched_category,
        matching_score = EXCLUDED.matching_score,
        fishing_score = EXCLUDED.fishing_score
""")


def _safe_float(val: str) -> float | None:
    if not val or val == "":
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def _safe_int(val: str) -> int | None:
    if not val or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def parse_csv_row(row: dict[str, str]) -> dict | None:
    """Parse a single CSV row into a dict ready for the INSERT statement."""
    scene_id = row.get("scene_id", "").strip()
    if not scene_id:
        return None

    lat = _safe_float(row.get("lat", ""))
    lon = _safe_float(row.get("lon", ""))
    if lat is None or lon is None:
        return None

    timestamp = row.get("timestamp", "").strip()
    if not timestamp:
        return None

    matched_category = row.get("matched_category", "").strip() or None
    is_dark = matched_category == "unmatched"

    mmsi = _safe_int(row.get("mmsi", ""))

    # scene_id is per SAR image, not per detection — multiple vessels per scene.
    # Create a unique detection ID from scene + position.
    detection_id = hashlib.sha256(
        f"{scene_id}:{lat}:{lon}".encode()
    ).hexdigest()[:24]

    return {
        "gfw_detection_id": detection_id,
        "detection_time": timestamp,
        "lat": lat,
        "lon": lon,
        "length_m": _safe_float(row.get("length_m", "")),
        "confidence": _safe_float(row.get("presence_score", "")),
        "is_dark": is_dark,
        "matched_mmsi": mmsi,
        "matched_category": matched_category,
        "matching_score": _safe_float(row.get("matching_score", "")),
        "fishing_score": _safe_float(row.get("fishing_score", "")),
    }


async def import_file(csv_path: Path, batch_size: int = 5000) -> int:
    """Import a single CSV file into the database. Returns rows imported."""
    logger.info("Importing %s ...", csv_path.name)

    session_factory = get_session()
    total = 0
    batch: list[dict] = []

    async def flush(session, rows: list[dict]) -> int:
        if not rows:
            return 0
        for row in rows:
            await session.execute(UPSERT_SQL, row)
        await session.commit()
        return len(rows)

    async with session_factory() as session:
        with open(csv_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                parsed = parse_csv_row(row)
                if parsed is None:
                    continue
                batch.append(parsed)

                if len(batch) >= batch_size:
                    total += await flush(session, batch)
                    if total % 50000 == 0:
                        logger.info("  %s: %d rows imported", csv_path.name, total)
                    batch = []

            # Flush remaining
            total += await flush(session, batch)

    logger.info("  %s: done — %d rows imported", csv_path.name, total)
    return total


async def main(data_dir: str, batch_size: int) -> None:
    data_path = Path(data_dir)
    if not data_path.is_dir():
        logger.error("Data directory not found: %s", data_dir)
        sys.exit(1)

    csv_files = sorted(data_path.glob("*.csv"))
    if not csv_files:
        logger.error("No CSV files found in %s", data_dir)
        sys.exit(1)

    logger.info("Found %d CSV files to import", len(csv_files))
    grand_total = 0

    for csv_file in csv_files:
        count = await import_file(csv_file, batch_size=batch_size)
        grand_total += count

    logger.info("Import complete: %d total rows imported", grand_total)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import GFW SAR CSV data")
    parser.add_argument(
        "--data-dir",
        default="data/gfw-sar",
        help="Directory containing SAR CSV files (default: data/gfw-sar)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Rows per batch commit (default: 5000)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.data_dir, args.batch_size))
