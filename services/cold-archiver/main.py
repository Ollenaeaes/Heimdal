"""Cold archiver — compresses old JSONL files to Parquet and drops old DB chunks.

Runs daily via cron.  Finds JSONL files older than cold_storage.age_days,
converts them to monthly Parquet files, deletes the originals, and drops
TimescaleDB chunks for positions older than the retention window.

Safety: JSONL files are only deleted if they have been loaded into the DB
by the batch-pipeline (tracked via /data/raw/meta/last_loaded.json).
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import sys
import zlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import asyncpg

from shared.config import settings
from shared.logging import setup_logging

logger = logging.getLogger("cold-archiver")

LAST_LOADED_PATH = Path("/data/raw/meta/last_loaded.json")


def get_loaded_files() -> set[str]:
    """Read the set of files the batch-pipeline has already loaded into the DB."""
    if not LAST_LOADED_PATH.exists():
        return set()
    try:
        with open(LAST_LOADED_PATH) as f:
            data = json.load(f)
        return set(data.get("loaded_files", []))
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to read last_loaded.json — treating all files as unloaded")
        return set()


def find_old_jsonl_files(base_path: str, age_days: int) -> list[Path]:
    """Find JSONL.gz files older than age_days."""
    raw_dir = Path(base_path) / "ais"
    if not raw_dir.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=age_days)
    old_files = []

    for gz_file in sorted(raw_dir.rglob("*.jsonl.gz")):
        # Extract date from filename: {type}_{YYYY}-{MM}-{DD}T{HH}.jsonl.gz
        try:
            name = gz_file.stem.replace(".jsonl", "")  # e.g. positions_2026-02-15T14
            date_part = name.split("_", 1)[1]  # 2026-02-15T14
            file_date = datetime.strptime(date_part, "%Y-%m-%dT%H").replace(
                tzinfo=timezone.utc
            )
            if file_date < cutoff:
                old_files.append(gz_file)
        except (ValueError, IndexError):
            logger.warning("Skipping file with unparseable name: %s", gz_file)

    logger.info("Found %d JSONL files older than %d days", len(old_files), age_days)
    return old_files


def group_files_by_day(files: list[Path]) -> dict[str, list[Path]]:
    """Group files by YYYY-MM-DD for daily Parquet output.

    Daily grouping keeps memory usage bounded — processing an entire month
    at once can OOM on the cold-archiver's 2 GB memory limit.
    """
    groups: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        # Extract YYYY/MM/DD from the directory path: .../ais/YYYY/MM/DD/...
        parts = f.parts
        try:
            ais_idx = parts.index("ais")
            year = parts[ais_idx + 1]
            month = parts[ais_idx + 2]
            day = parts[ais_idx + 3]
            groups[f"{year}-{month}-{day}"].append(f)
        except (ValueError, IndexError):
            logger.warning("Cannot determine day for file: %s", f)
    return dict(groups)


PARQUET_SCHEMA = None  # Initialized lazily

BATCH_SIZE = 50_000  # Rows per write batch — keeps memory bounded


def _get_parquet_schema():
    import pyarrow as pa

    global PARQUET_SCHEMA
    if PARQUET_SCHEMA is None:
        PARQUET_SCHEMA = pa.schema([
            ("_raw", pa.string()),
            ("_received_at", pa.string()),
            ("message_type", pa.string()),
            ("mmsi", pa.int32()),
        ])
    return PARQUET_SCHEMA


def convert_to_parquet(
    files: list[Path], output_dir: Path, day_key: str, file_type: str
) -> Path | None:
    """Convert JSONL.gz files to Parquet using streaming writes.

    Processes one file at a time and flushes in batches to keep memory bounded.
    Returns the path to the created Parquet file, or None on failure.
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        logger.error("pyarrow not installed — cannot create Parquet files")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{file_type}_{day_key}.parquet"

    schema = _get_parquet_schema()
    total_rows = 0
    writer = None

    try:
        for filepath in files:
            batch_raw: list[str] = []
            batch_received: list[str] = []
            batch_type: list[str] = []
            batch_mmsi: list[int | None] = []

            try:
                with gzip.open(filepath, "rb") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = json.loads(line)
                            batch_raw.append(line.decode("utf-8"))
                            batch_received.append(msg.get("_received_at", ""))
                            batch_type.append(msg.get("MessageType", ""))
                            batch_mmsi.append((msg.get("MetaData") or {}).get("MMSI"))
                        except (json.JSONDecodeError, ValueError):
                            continue

                        if len(batch_raw) >= BATCH_SIZE:
                            table = pa.table(
                                {"_raw": batch_raw, "_received_at": batch_received,
                                 "message_type": batch_type, "mmsi": pa.array(batch_mmsi, type=pa.int32())},
                                schema=schema,
                            )
                            if writer is None:
                                writer = pq.ParquetWriter(str(output_path), schema,
                                                          compression=settings.cold_storage.compression)
                            writer.write_table(table)
                            total_rows += len(batch_raw)
                            batch_raw.clear()
                            batch_received.clear()
                            batch_type.clear()
                            batch_mmsi.clear()

            except (gzip.BadGzipFile, OSError, zlib.error) as e:
                logger.warning("Failed to read %s: %s", filepath, e)

            # Flush remaining rows from this file
            if batch_raw:
                table = pa.table(
                    {"_raw": batch_raw, "_received_at": batch_received,
                     "message_type": batch_type, "mmsi": pa.array(batch_mmsi, type=pa.int32())},
                    schema=schema,
                )
                if writer is None:
                    writer = pq.ParquetWriter(str(output_path), schema,
                                              compression=settings.cold_storage.compression)
                writer.write_table(table)
                total_rows += len(batch_raw)

    finally:
        if writer is not None:
            writer.close()

    if total_rows == 0:
        logger.info("No rows to write for %s %s", file_type, day_key)
        # Clean up empty file if created
        if output_path.exists():
            output_path.unlink()
        return None

    logger.info(
        "Created Parquet file: %s (%d rows, %.1f MB)",
        output_path,
        total_rows,
        output_path.stat().st_size / (1024 * 1024),
    )
    return output_path


async def drop_old_db_chunks(pool: asyncpg.Pool, retention_days: int) -> None:
    """Drop TimescaleDB chunks older than retention_days."""
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT drop_chunks('vessel_positions', older_than => $1::interval)",
            f"{retention_days} days",
        )
        logger.info("Dropped old DB chunks (retention=%d days): %s", retention_days, result)


async def main():
    setup_logging("cold-archiver")
    logger.info("Starting cold archiver run")

    base_path = settings.raw_storage.base_path
    age_days = settings.cold_storage.age_days
    retain_jsonl_days = settings.cold_storage.retain_jsonl_days

    # Load the set of files already ingested into the DB by batch-pipeline
    loaded_files = get_loaded_files()
    if not loaded_files:
        logger.warning(
            "No loaded files tracked in last_loaded.json — will archive to "
            "Parquet but will NOT delete any JSONL files (safety guard)"
        )

    # Find old JSONL files
    old_files = find_old_jsonl_files(base_path, age_days)
    if not old_files:
        logger.info("No files old enough to archive")
    else:
        # Group by day to keep memory usage bounded
        by_day = group_files_by_day(old_files)

        for day_key, day_files in sorted(by_day.items()):
            # Separate by file type (positions, static, other)
            by_type: dict[str, list[Path]] = defaultdict(list)
            for f in day_files:
                name = f.stem.replace(".jsonl", "")
                file_type = name.split("_", 1)[0]  # positions, static, other
                by_type[file_type].append(f)

            # Output: /data/raw/cold/ais/YYYY/MM/DD/
            cold_dir = Path(base_path) / "cold" / "ais" / day_key.replace("-", "/")

            for file_type, type_files in by_type.items():
                parquet_path = convert_to_parquet(
                    type_files, cold_dir, day_key, file_type
                )
                if parquet_path is not None:
                    # Delete original JSONL files only after:
                    # 1. Successful Parquet creation (above)
                    # 2. File age exceeds age_days + retain_jsonl_days
                    # 3. SAFETY: batch-pipeline has loaded the file into the DB
                    delete_cutoff = datetime.now(timezone.utc) - timedelta(
                        days=age_days + retain_jsonl_days
                    )
                    for f in type_files:
                        try:
                            name = f.stem.replace(".jsonl", "")
                            date_part = name.split("_", 1)[1]
                            file_date = datetime.strptime(
                                date_part, "%Y-%m-%dT%H"
                            ).replace(tzinfo=timezone.utc)
                            if file_date >= delete_cutoff:
                                continue
                            if str(f) not in loaded_files:
                                logger.warning(
                                    "SKIPPING deletion of %s — not yet loaded into DB",
                                    f,
                                )
                                continue
                            f.unlink()
                            logger.info("Deleted archived JSONL: %s", f)
                        except (ValueError, IndexError, OSError) as e:
                            logger.warning("Failed to process %s: %s", f, e)

    # Drop old DB chunks
    dsn = settings.database_url.get_secret_value().replace("+asyncpg", "")
    try:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
        await drop_old_db_chunks(pool, settings.retention.positions_days)
        await pool.close()
    except Exception:
        logger.exception("Failed to drop old DB chunks")

    logger.info("Cold archiver run complete")


if __name__ == "__main__":
    asyncio.run(main())
