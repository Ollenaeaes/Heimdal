#!/usr/bin/env python3
"""Export the FalkorDB graph and vessel_signals for VPS transfer (Story 9).

Exports:
  1. FalkorDB graph → RDB dump file (via redis-cli --rdb)
  2. vessel_signals table → SQL dump file (via pg_dump)

Usage:
    python scripts/export_graph.py
    python scripts/export_graph.py --output-dir /tmp/graph-export
    python scripts/export_graph.py --graph-only
    python scripts/export_graph.py --signals-only
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
logger = logging.getLogger("export-graph")


def _get_sync_dsn() -> str:
    url = os.environ.get("DATABASE_URL", settings.database_url.get_secret_value())
    return re.sub(r"postgresql\+asyncpg://", "postgresql://", url)


def export_falkordb_graph(output_dir: Path) -> Path:
    """Export FalkorDB graph as an RDB dump file.

    Uses redis-cli --rdb to dump the FalkorDB data file.
    FalkorDB runs on the configured port (default 6380).
    """
    dump_path = output_dir / "falkordb_heimdal.rdb"
    host = settings.falkordb.host
    port = settings.falkordb.port

    logger.info("Exporting FalkorDB graph from %s:%d to %s", host, port, dump_path)

    try:
        result = subprocess.run(
            ["redis-cli", "-h", host, "-p", str(port), "--rdb", str(dump_path)],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            logger.error("redis-cli --rdb failed: %s", result.stderr)
            raise RuntimeError(f"FalkorDB export failed: {result.stderr}")

        size = dump_path.stat().st_size
        logger.info("FalkorDB export complete: %s (%.1f MB)", dump_path, size / 1024 / 1024)
        return dump_path

    except FileNotFoundError:
        logger.error("redis-cli not found — install Redis CLI tools")
        raise


def export_vessel_signals(output_dir: Path) -> Path:
    """Export vessel_signals table as a PostgreSQL custom dump."""
    dump_path = output_dir / "vessel_signals.dump"
    dsn = _get_sync_dsn()

    logger.info("Exporting vessel_signals to %s", dump_path)

    try:
        result = subprocess.run(
            ["pg_dump", dsn, "--table=vessel_signals", "-Fc", "-f", str(dump_path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            logger.error("pg_dump failed: %s", result.stderr)
            raise RuntimeError(f"vessel_signals export failed: {result.stderr}")

        size = dump_path.stat().st_size
        logger.info("vessel_signals export complete: %s (%.1f KB)", dump_path, size / 1024)
        return dump_path

    except FileNotFoundError:
        logger.error("pg_dump not found — install PostgreSQL client tools")
        raise


def verify_export(output_dir: Path) -> dict:
    """Verify exported files exist and are non-empty."""
    results = {}

    rdb_path = output_dir / "falkordb_heimdal.rdb"
    if rdb_path.exists() and rdb_path.stat().st_size > 0:
        results["graph"] = {"path": str(rdb_path), "size_bytes": rdb_path.stat().st_size}
    else:
        results["graph"] = {"error": "Missing or empty"}

    dump_path = output_dir / "vessel_signals.dump"
    if dump_path.exists() and dump_path.stat().st_size > 0:
        results["signals"] = {"path": str(dump_path), "size_bytes": dump_path.stat().st_size}
    else:
        results["signals"] = {"error": "Missing or empty"}

    return results


def main():
    parser = argparse.ArgumentParser(description="Export graph and signals for VPS transfer")
    parser.add_argument("--output-dir", type=Path, default=Path("data/graph-export"),
                        help="Output directory (default: data/graph-export)")
    parser.add_argument("--graph-only", action="store_true", help="Only export FalkorDB graph")
    parser.add_argument("--signals-only", action="store_true", help="Only export vessel_signals")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    if not args.signals_only:
        export_falkordb_graph(args.output_dir)

    if not args.graph_only:
        export_vessel_signals(args.output_dir)

    elapsed = time.time() - t0
    verification = verify_export(args.output_dir)

    logger.info("Export complete in %.1fs", elapsed)
    for name, info in verification.items():
        if "error" in info:
            logger.warning("  %s: %s", name, info["error"])
        else:
            logger.info("  %s: %s (%.1f KB)", name, info["path"], info["size_bytes"] / 1024)

    print(f"\nExported to: {args.output_dir}")
    print("Transfer to VPS: scp -r {} root@<vps-ip>:/data/graph-import/".format(args.output_dir))


if __name__ == "__main__":
    main()
