#!/usr/bin/env python3
"""
Historical batch load for OpenSanctions entity graph.

Parses the full OpenSanctions FTM dataset and loads entities, relationships,
and vessel links into the os_entities, os_relationships, and os_vessel_links
tables. Supports upsert (safe to re-run).

Usage:
    python3 scripts/load_opensanctions.py [options]

Options:
    --file FILE       Path to default.json (default: data/opensanctions/default.json)
    --db-url URL      Database URL (default from DATABASE_URL env var)
    --batch-size N    Records per batch (default: 5000)
    --stats           Print stats summary and exit (after loading)
    --stats-only      Print stats from existing DB data without loading
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.parsers.opensanctions_ftm import (
    ExtractionBatch,
    ExtractorStats,
    stream_extract,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_DATA_PATH = os.environ.get(
    "OPENSANCTIONS_DATA_PATH", str(PROJECT_ROOT / "data" / "opensanctions")
)


def get_db_connection(db_url: str):
    """Create a psycopg2 connection."""
    import psycopg2
    # Convert async URL to sync if needed
    url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    return psycopg2.connect(url)


def persist_batch(conn, batch: ExtractionBatch) -> dict[str, int]:
    """Persist a batch of extracted records to the database.

    Uses ON CONFLICT upserts so re-runs are safe.

    Returns:
        Dict with counts of entities, relationships, and vessel_links persisted.
    """
    cur = conn.cursor()
    counts = {"entities": 0, "relationships": 0, "vessel_links": 0}

    # Upsert entities
    for entity in batch.entities:
        cur.execute(
            """
            INSERT INTO os_entities (entity_id, schema_type, name, properties, topics, target, first_seen, last_seen, dataset)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), %s)
            ON CONFLICT (entity_id) DO UPDATE SET
                schema_type = EXCLUDED.schema_type,
                name = EXCLUDED.name,
                properties = EXCLUDED.properties,
                topics = EXCLUDED.topics,
                target = EXCLUDED.target,
                last_seen = NOW(),
                dataset = EXCLUDED.dataset
            """,
            (
                entity.entity_id,
                entity.schema_type,
                entity.name,
                json.dumps(entity.properties),
                entity.topics,
                entity.target,
                entity.dataset,
            ),
        )
        counts["entities"] += 1

    # Upsert relationships
    for rel in batch.relationships:
        cur.execute(
            """
            INSERT INTO os_relationships (rel_type, source_entity_id, target_entity_id, properties, first_seen, last_seen)
            VALUES (%s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (rel_type, source_entity_id, target_entity_id) DO UPDATE SET
                properties = EXCLUDED.properties,
                last_seen = NOW()
            """,
            (
                rel.rel_type,
                rel.source_entity_id,
                rel.target_entity_id,
                json.dumps(rel.properties),
            ),
        )
        counts["relationships"] += 1

    # Upsert vessel links
    for link in batch.vessel_links:
        cur.execute(
            """
            INSERT INTO os_vessel_links (entity_id, imo, mmsi, confidence, match_method)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (entity_id, match_method) DO UPDATE SET
                imo = EXCLUDED.imo,
                mmsi = EXCLUDED.mmsi,
                confidence = EXCLUDED.confidence
            """,
            (
                link.entity_id,
                link.imo,
                link.mmsi,
                link.confidence,
                link.match_method,
            ),
        )
        counts["vessel_links"] += 1

    cur.close()
    conn.commit()
    return counts


def print_db_stats(conn) -> None:
    """Print stats from existing database data."""
    cur = conn.cursor()

    # Total entities
    cur.execute("SELECT COUNT(*) FROM os_entities")
    total_entities = cur.fetchone()[0]
    print(f"\nTotal entities: {total_entities}")

    # Entities by type
    cur.execute("SELECT schema_type, COUNT(*) FROM os_entities GROUP BY schema_type ORDER BY COUNT(*) DESC")
    print("\nEntities by type:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")

    # Total relationships
    cur.execute("SELECT COUNT(*) FROM os_relationships")
    total_rels = cur.fetchone()[0]
    print(f"\nTotal relationships: {total_rels}")

    # Relationships by type
    cur.execute("SELECT rel_type, COUNT(*) FROM os_relationships GROUP BY rel_type ORDER BY COUNT(*) DESC")
    print("\nRelationships by type:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")

    # Vessel links
    cur.execute("SELECT COUNT(*) FROM os_vessel_links")
    total_links = cur.fetchone()[0]
    print(f"\nTotal vessel links: {total_links}")

    # Vessel links by method
    cur.execute("SELECT match_method, COUNT(*) FROM os_vessel_links GROUP BY match_method ORDER BY COUNT(*) DESC")
    print("\nVessel links by method:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")

    # Target entities (directly sanctioned)
    cur.execute("SELECT COUNT(*) FROM os_entities WHERE target = TRUE")
    target_count = cur.fetchone()[0]
    print(f"\nDirectly sanctioned/listed entities: {target_count}")

    cur.close()


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Load OpenSanctions entity graph")
    parser.add_argument("--file", type=str, help="Path to default.json NDJSON file")
    parser.add_argument("--db-url", type=str, help="Database URL")
    parser.add_argument("--batch-size", type=int, default=5000, help="Records per batch")
    parser.add_argument("--stats", action="store_true", help="Print stats after loading")
    parser.add_argument("--stats-only", action="store_true", help="Print DB stats without loading")
    args = parser.parse_args()

    db_url = args.db_url or os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL not set. Use --db-url or set DATABASE_URL env var.")

    conn = get_db_connection(db_url)

    try:
        if args.stats_only:
            print_db_stats(conn)
            return

        # Determine file path
        filepath = args.file or os.path.join(DEFAULT_DATA_PATH, "default.json")
        filepath = Path(filepath)
        if not filepath.exists():
            raise SystemExit(f"Data file not found: {filepath}\nRun scripts/download-opensanctions.sh first.")

        logger.info("Loading OpenSanctions from %s", filepath)
        start_time = time.monotonic()
        totals = {"entities": 0, "relationships": 0, "vessel_links": 0}

        for batch, stats in stream_extract(filepath, batch_size=args.batch_size):
            counts = persist_batch(conn, batch)
            for key in totals:
                totals[key] += counts[key]
            logger.info(
                "Progress: %d lines processed, %d entities, %d relationships, %d vessel links",
                stats.lines_processed, totals["entities"], totals["relationships"], totals["vessel_links"],
            )

        elapsed = time.monotonic() - start_time
        logger.info(
            "Load complete in %.1fs: %d entities, %d relationships, %d vessel links",
            elapsed, totals["entities"], totals["relationships"], totals["vessel_links"],
        )

        if args.stats:
            print_db_stats(conn)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
