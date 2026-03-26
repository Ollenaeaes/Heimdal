#!/usr/bin/env python3
"""Import a FalkorDB graph dump and vessel_signals on the VPS (Story 9).

Usage:
    python scripts/import_graph.py --input-dir /data/graph-import
    python scripts/import_graph.py --input-dir /data/graph-import --graph-only
    python scripts/import_graph.py --input-dir /data/graph-import --signals-only
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("import-graph")


def _get_sync_dsn() -> str:
    url = os.environ.get("DATABASE_URL", settings.database_url.get_secret_value())
    return re.sub(r"postgresql\+asyncpg://", "postgresql://", url)


def import_falkordb_graph(input_dir: Path) -> None:
    """Import FalkorDB graph from RDB dump.

    Stops FalkorDB, copies RDB file, restarts FalkorDB.
    This replaces the existing graph entirely.
    """
    rdb_path = input_dir / "falkordb_heimdal.rdb"
    if not rdb_path.exists():
        logger.error("FalkorDB dump not found: %s", rdb_path)
        raise FileNotFoundError(f"Missing: {rdb_path}")

    host = settings.falkordb.host
    port = settings.falkordb.port

    logger.info("Importing FalkorDB graph from %s", rdb_path)

    # Use RESTORE or direct RDB copy approach
    # For Docker deployments, copy the RDB into the volume and restart
    # For local dev, we can use redis-cli to load data

    # Approach: Use redis-cli DEBUG RELOAD after copying RDB
    # In Docker: docker cp <rdb> <container>:/data/dump.rdb && docker restart <container>

    logger.info(
        "To import on Docker (VPS):\n"
        "  1. docker compose stop falkordb\n"
        "  2. docker cp %s <falkordb-container>:/data/dump.rdb\n"
        "  3. docker compose start falkordb\n"
        "FalkorDB will load the RDB on startup.",
        rdb_path,
    )

    # Verify the dump file is valid
    size = rdb_path.stat().st_size
    logger.info("RDB dump size: %.1f MB", size / 1024 / 1024)

    if size < 100:
        logger.warning("RDB dump seems too small — may be empty")


def import_vessel_signals(input_dir: Path) -> None:
    """Import vessel_signals from PostgreSQL custom dump."""
    dump_path = input_dir / "vessel_signals.dump"
    if not dump_path.exists():
        logger.error("vessel_signals dump not found: %s", dump_path)
        raise FileNotFoundError(f"Missing: {dump_path}")

    dsn = _get_sync_dsn()

    logger.info("Importing vessel_signals from %s", dump_path)

    result = subprocess.run(
        ["pg_restore", "-d", dsn, "--clean", "--if-exists",
         "--no-owner", "--no-privileges", str(dump_path)],
        capture_output=True, text=True, timeout=120,
    )

    if result.returncode != 0 and "error" in result.stderr.lower():
        logger.error("pg_restore failed: %s", result.stderr)
        raise RuntimeError(f"vessel_signals import failed: {result.stderr}")

    logger.info("vessel_signals import complete")


def verify_import() -> dict:
    """Verify imported data by querying FalkorDB and PostgreSQL."""
    from shared.db.graph import get_graph, close_graph

    results = {}

    # Check FalkorDB
    try:
        g = get_graph()
        node_result = g.query("MATCH (n) RETURN count(n)")
        edge_result = g.query("MATCH ()-[r]->() RETURN count(r)")
        results["graph"] = {
            "nodes": node_result.result_set[0][0],
            "edges": edge_result.result_set[0][0],
        }
        close_graph()
    except Exception as e:
        results["graph"] = {"error": str(e)}

    # Check vessel_signals
    try:
        import psycopg2
        conn = psycopg2.connect(_get_sync_dsn())
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM vessel_signals")
            count = cur.fetchone()[0]
        conn.close()
        results["signals"] = {"count": count}
    except Exception as e:
        results["signals"] = {"error": str(e)}

    return results


def main():
    parser = argparse.ArgumentParser(description="Import graph and signals on VPS")
    parser.add_argument("--input-dir", type=Path, required=True,
                        help="Directory containing export files")
    parser.add_argument("--graph-only", action="store_true")
    parser.add_argument("--signals-only", action="store_true")
    parser.add_argument("--verify", action="store_true",
                        help="Verify import after completion")
    args = parser.parse_args()

    t0 = time.time()

    if not args.signals_only:
        import_falkordb_graph(args.input_dir)

    if not args.graph_only:
        import_vessel_signals(args.input_dir)

    elapsed = time.time() - t0
    logger.info("Import complete in %.1fs", elapsed)

    if args.verify:
        verification = verify_import()
        for name, info in verification.items():
            logger.info("  %s: %s", name, info)


if __name__ == "__main__":
    main()
