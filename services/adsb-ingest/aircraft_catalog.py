"""Aircraft of interest catalog.

Loads the curated CSV into memory as a hash map keyed by ICAO hex,
and syncs it to the aircraft_of_interest database table on startup.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import asyncpg

logger = logging.getLogger("adsb-ingest.catalog")

# Path inside Docker container (CSV is copied during build)
CSV_PATH = Path("/app/data/heimdal_aircraft_of_interest.csv")
# Fallback for local development
CSV_PATH_LOCAL = Path(__file__).parent.parent.parent / "data" / "adsb" / "heimdal_aircraft_of_interest.csv"


def load_csv() -> dict[str, dict]:
    """Load the aircraft CSV into a dict keyed by lowercase ICAO hex."""
    path = CSV_PATH if CSV_PATH.exists() else CSV_PATH_LOCAL
    if not path.exists():
        logger.warning("Aircraft CSV not found at %s or %s", CSV_PATH, CSV_PATH_LOCAL)
        return {}

    catalog: dict[str, dict] = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hex_code = row.get("icao_hex", "").strip().lower()
            if not hex_code:
                continue
            catalog[hex_code] = {
                "icao_hex": hex_code,
                "registration": row.get("registration", "").strip() or None,
                "type_code": row.get("type", "").strip() or None,
                "description": row.get("description", "").strip() or None,
                "country": row.get("country", "").strip() or None,
                "category": row.get("category", "").strip() or None,
                "role": row.get("role", "").strip() or None,
                "source": row.get("source", "").strip() or None,
            }
    logger.info("Loaded %d aircraft of interest from %s", len(catalog), path)
    return catalog


async def sync_to_db(pool: asyncpg.Pool, catalog: dict[str, dict]) -> None:
    """Upsert all aircraft of interest into the database table."""
    if not catalog:
        return

    async with pool.acquire() as conn:
        await conn.executemany(
            """INSERT INTO aircraft_of_interest
               (icao_hex, registration, type_code, description, country, category, role, source, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
               ON CONFLICT (icao_hex) DO UPDATE SET
                 registration = COALESCE(EXCLUDED.registration, aircraft_of_interest.registration),
                 type_code = COALESCE(EXCLUDED.type_code, aircraft_of_interest.type_code),
                 description = COALESCE(EXCLUDED.description, aircraft_of_interest.description),
                 country = COALESCE(EXCLUDED.country, aircraft_of_interest.country),
                 category = COALESCE(EXCLUDED.category, aircraft_of_interest.category),
                 role = COALESCE(EXCLUDED.role, aircraft_of_interest.role),
                 source = COALESCE(EXCLUDED.source, aircraft_of_interest.source),
                 updated_at = NOW()""",
            [
                (
                    ac["icao_hex"], ac["registration"], ac["type_code"],
                    ac["description"], ac["country"], ac["category"],
                    ac["role"], ac["source"],
                )
                for ac in catalog.values()
            ],
        )
    logger.info("Synced %d aircraft of interest to database", len(catalog))
