"""JSONL file loader — reads raw AIS files and bulk-inserts into the database.

Reads gzipped JSONL files written by the ais-fetcher service, parses each
line using the existing AIS parser, and bulk-inserts positions and vessel
profile updates into PostgreSQL via asyncpg.

Tracks which files have been loaded via /data/raw/meta/last_loaded.json
so that re-runs only process new files.
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

try:
    import orjson

    def _json_loads(data: bytes | str) -> dict:
        return orjson.loads(data)

    def _json_dumps(obj: dict) -> str:
        return orjson.dumps(obj).decode("utf-8")

except ImportError:
    _json_loads = json.loads

    def _json_dumps(obj: dict) -> str:
        return json.dumps(obj)

import asyncpg

logger = logging.getLogger("batch-pipeline.loader")

# Path to the file tracking which JSONL files have been loaded
LAST_LOADED_PATH = Path("/data/raw/meta/last_loaded.json")


def get_loaded_files() -> set[str]:
    """Read the set of already-loaded file paths from last_loaded.json."""
    if not LAST_LOADED_PATH.exists():
        return set()
    try:
        with open(LAST_LOADED_PATH) as f:
            data = json.load(f)
        return set(data.get("loaded_files", []))
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to read last_loaded.json, starting fresh")
        return set()


def mark_files_loaded(files: list[str]) -> None:
    """Update last_loaded.json with newly loaded files."""
    existing = get_loaded_files()
    existing.update(files)
    LAST_LOADED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LAST_LOADED_PATH, "w") as f:
        json.dump(
            {"loaded_files": sorted(existing), "last_updated": datetime.now(timezone.utc).isoformat()},
            f,
            indent=2,
        )


def find_unloaded_files(base_path: str = "/data/raw") -> list[Path]:
    """Find all JSONL.gz files that haven't been loaded yet, sorted by name (chronological)."""
    raw_dir = Path(base_path) / "ais"
    if not raw_dir.exists():
        logger.info("No raw AIS directory found at %s", raw_dir)
        return []

    loaded = get_loaded_files()
    unloaded = []
    for gz_file in sorted(raw_dir.rglob("*.jsonl.gz")):
        if str(gz_file) not in loaded:
            unloaded.append(gz_file)

    logger.info("Found %d unloaded JSONL files", len(unloaded))
    return unloaded


def read_jsonl_file(filepath: Path) -> list[dict]:
    """Read and parse all lines from a gzipped JSONL file."""
    messages = []
    try:
        with gzip.open(filepath, "rb") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = _json_loads(line)
                    messages.append(msg)
                except (json.JSONDecodeError, ValueError):
                    logger.warning("Invalid JSON at %s:%d", filepath, line_num)
    except EOFError:
        # File is still being written by ais-fetcher — return what we got so far
        logger.info("File %s is still being written, read %d messages so far", filepath, len(messages))
    except (gzip.BadGzipFile, OSError) as e:
        logger.error("Failed to read %s: %s", filepath, e)
    return messages


async def load_positions_to_db(
    pool: asyncpg.Pool,
    messages: list[dict],
    parser_module,
) -> tuple[int, set[int]]:
    """Parse position messages and bulk-insert into vessel_positions.

    Returns (count_inserted, set_of_mmsis_with_new_data).
    """
    from shared.models.ais_message import PositionReport, ShipStaticData

    position_rows = []
    vessel_updates: dict[int, dict] = {}
    mmsis_with_data: set[int] = set()

    for raw in messages:
        result = parser_module.parse_message(raw)
        if result is None:
            continue

        if isinstance(result, PositionReport):
            position_rows.append((
                result.timestamp,
                result.mmsi,
                result.longitude,
                result.latitude,
                result.sog,
                result.cog,
                result.heading,
                result.nav_status,
                result.rot,
                None,  # draught
            ))
            mmsis_with_data.add(result.mmsi)

        elif isinstance(result, ShipStaticData):
            extras = parser_module.parse_vessel_extras(raw)
            extras["mmsi"] = result.mmsi
            if result.imo:
                extras["imo"] = result.imo
            if result.ship_name:
                extras["ship_name"] = result.ship_name
            if result.ship_type is not None:
                extras["ship_type"] = result.ship_type
            vessel_updates[result.mmsi] = extras
            mmsis_with_data.add(result.mmsi)

    if not position_rows and not vessel_updates:
        return 0, mmsis_with_data

    async with pool.acquire() as conn:
        # Bulk insert positions
        if position_rows:
            await conn.executemany(
                """INSERT INTO vessel_positions
                   (timestamp, mmsi, position, sog, cog, heading,
                    nav_status, rot, draught)
                   VALUES ($1, $2,
                           ST_SetSRID(ST_MakePoint($3, $4), 4326)::geography,
                           $5, $6, $7, $8, $9, $10)
                   ON CONFLICT DO NOTHING""",
                position_rows,
            )

            # Update last_position for each vessel
            # Group by mmsi and take the latest timestamp
            latest_positions: dict[int, tuple] = {}
            for row in position_rows:
                mmsi = row[1]
                if mmsi not in latest_positions or row[0] > latest_positions[mmsi][0]:
                    latest_positions[mmsi] = row

            for row in latest_positions.values():
                await conn.execute(
                    """UPDATE vessel_profiles
                       SET last_position_time = $1,
                           last_lat = $2,
                           last_lon = $3,
                           updated_at = NOW()
                       WHERE mmsi = $4
                         AND (last_position_time IS NULL OR last_position_time < $1)""",
                    row[0], row[3], row[2], row[1],
                )

        # Upsert vessel profiles
        for mmsi, data in vessel_updates.items():
            data["mmsi"] = mmsi
            cols = list(data.keys())
            vals = [data[c] for c in cols]
            placeholders = [f"${i + 1}" for i in range(len(cols))]
            updates = [
                f"{c} = COALESCE(EXCLUDED.{c}, vessel_profiles.{c})"
                for c in cols
                if c != "mmsi"
            ]
            updates.append("updated_at = NOW()")

            sql = (
                f"INSERT INTO vessel_profiles ({', '.join(cols)})"
                f" VALUES ({', '.join(placeholders)})"
                f" ON CONFLICT (mmsi) DO UPDATE SET {', '.join(updates)}"
            )
            await conn.execute(sql, *vals)

    logger.info(
        "Loaded %d positions, %d vessel updates, %d unique MMSIs",
        len(position_rows),
        len(vessel_updates),
        len(mmsis_with_data),
    )
    return len(position_rows), mmsis_with_data
