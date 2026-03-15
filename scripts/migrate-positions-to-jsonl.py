#!/usr/bin/env python3
"""Migrate existing vessel_positions from TimescaleDB to JSONL/Parquet files.

One-time migration script that exports historical position data from the
database into the raw file structure used by the new batch architecture.

Usage:
    python scripts/migrate-positions-to-jsonl.py

Environment:
    DATABASE_URL: PostgreSQL connection string (default: from config)

The script:
  1. Queries vessel_positions in hourly chunks
  2. Writes recent data (<30 days) as JSONL.gz files
  3. Writes older data (>30 days) directly as Parquet
  4. Updates last_loaded.json so batch-pipeline doesn't re-import
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Project imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate")

BASE_PATH = os.environ.get("RAW_STORAGE_PATH", "/data/raw")
COLD_AGE_DAYS = 30


async def export_positions(dsn: str) -> None:
    """Export all positions from the database to JSONL/Parquet files."""
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3)

    # Get time range of existing data
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT MIN(timestamp) as min_ts, MAX(timestamp) as max_ts, COUNT(*) as total "
            "FROM vessel_positions"
        )

    if not row or row["total"] == 0:
        logger.info("No positions in database, nothing to migrate")
        await pool.close()
        return

    min_ts = row["min_ts"]
    max_ts = row["max_ts"]
    total = row["total"]
    logger.info(
        "Migrating %d positions from %s to %s",
        total, min_ts.isoformat(), max_ts.isoformat(),
    )

    now = datetime.now(timezone.utc)
    cold_cutoff = now - timedelta(days=COLD_AGE_DAYS)

    # Process hour by hour
    current = min_ts.replace(minute=0, second=0, microsecond=0)
    exported_count = 0
    files_written: list[str] = []
    parquet_months: dict[str, list[dict]] = defaultdict(list)

    while current <= max_ts:
        hour_end = current + timedelta(hours=1)

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT timestamp, mmsi,
                          ST_X(position::geometry) as lon,
                          ST_Y(position::geometry) as lat,
                          sog, cog, heading, nav_status, rot, draught
                   FROM vessel_positions
                   WHERE timestamp >= $1 AND timestamp < $2
                   ORDER BY timestamp""",
                current, hour_end,
            )

        if not rows:
            current = hour_end
            continue

        # Build reconstructed raw-ish JSON messages
        messages = []
        for r in rows:
            msg = {
                "MessageType": "PositionReport",
                "MetaData": {
                    "MMSI": r["mmsi"],
                    "time_utc": r["timestamp"].isoformat(),
                },
                "Message": {
                    "PositionReport": {
                        "Latitude": r["lat"],
                        "Longitude": r["lon"],
                        "Sog": r["sog"],
                        "Cog": r["cog"],
                        "TrueHeading": r["heading"],
                        "NavigationalStatus": r["nav_status"],
                        "RateOfTurn": r["rot"],
                    }
                },
                "_received_at": r["timestamp"].isoformat(),
                "_migrated": True,
            }
            messages.append(msg)

        if current < cold_cutoff:
            # Old data -> accumulate for monthly Parquet
            month_key = current.strftime("%Y-%m")
            for msg in messages:
                parquet_months[month_key].append({
                    "_raw": json.dumps(msg),
                    "_received_at": msg["_received_at"],
                    "message_type": "PositionReport",
                    "mmsi": msg["MetaData"]["MMSI"],
                })
        else:
            # Recent data -> write JSONL.gz
            hour_key = current.strftime("%Y-%m-%dT%H")
            day_dir = (
                Path(BASE_PATH) / "ais"
                / current.strftime("%Y")
                / current.strftime("%m")
                / current.strftime("%d")
            )
            day_dir.mkdir(parents=True, exist_ok=True)

            filepath = day_dir / f"positions_{hour_key}.jsonl.gz"
            with gzip.open(filepath, "ab", compresslevel=6) as f:
                for msg in messages:
                    f.write(json.dumps(msg).encode("utf-8") + b"\n")

            files_written.append(str(filepath))
            logger.info("Wrote %d positions to %s", len(messages), filepath)

        exported_count += len(rows)
        if exported_count % 100000 == 0:
            logger.info("Progress: %d / %d positions exported", exported_count, total)

        current = hour_end

    # Write accumulated Parquet files for cold data
    if parquet_months:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq

            for month_key, month_rows in sorted(parquet_months.items()):
                year, month = month_key.split("-")
                cold_dir = Path(BASE_PATH) / "cold" / "ais" / year / month
                cold_dir.mkdir(parents=True, exist_ok=True)

                output_path = cold_dir / f"positions_{month_key}.parquet"

                table = pa.table({
                    "_raw": pa.array([r["_raw"] for r in month_rows], type=pa.string()),
                    "_received_at": pa.array([r["_received_at"] for r in month_rows], type=pa.string()),
                    "message_type": pa.array([r["message_type"] for r in month_rows], type=pa.string()),
                    "mmsi": pa.array([r["mmsi"] for r in month_rows], type=pa.int32()),
                })

                pq.write_table(table, output_path, compression="snappy")
                logger.info(
                    "Wrote %d positions to Parquet: %s (%.1f MB)",
                    len(month_rows),
                    output_path,
                    output_path.stat().st_size / (1024 * 1024),
                )
        except ImportError:
            logger.warning(
                "pyarrow not installed — writing cold data as JSONL instead of Parquet"
            )
            for month_key, month_rows in sorted(parquet_months.items()):
                year, month = month_key.split("-")
                cold_dir = Path(BASE_PATH) / "cold" / "ais" / year / month
                cold_dir.mkdir(parents=True, exist_ok=True)
                filepath = cold_dir / f"positions_{month_key}.jsonl.gz"
                with gzip.open(filepath, "ab", compresslevel=6) as f:
                    for row in month_rows:
                        f.write(row["_raw"].encode("utf-8") + b"\n")
                files_written.append(str(filepath))

    # Update last_loaded.json so batch-pipeline doesn't re-import
    meta_path = Path(BASE_PATH) / "meta" / "last_loaded.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    existing_loaded: set[str] = set()
    if meta_path.exists():
        with open(meta_path) as f:
            data = json.load(f)
            existing_loaded = set(data.get("loaded_files", []))

    existing_loaded.update(files_written)
    with open(meta_path, "w") as f:
        json.dump(
            {
                "loaded_files": sorted(existing_loaded),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "migration_note": "Initial migration from TimescaleDB",
            },
            f,
            indent=2,
        )

    await pool.close()
    logger.info(
        "Migration complete: %d positions exported, %d JSONL files, %d Parquet months",
        exported_count,
        len(files_written),
        len(parquet_months),
    )


async def main():
    from shared.config import settings
    dsn = settings.database_url.get_secret_value().replace("+asyncpg", "")
    await export_positions(dsn)


if __name__ == "__main__":
    asyncio.run(main())
