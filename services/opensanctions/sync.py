#!/usr/bin/env python3
"""Daily OpenSanctions entity graph sync.

Downloads the latest OpenSanctions default dataset and upserts all entities,
relationships, and vessel links. Entities not present in the new dataset are
NOT deleted (OpenSanctions occasionally removes and re-adds entities).

Designed to run as a scheduled batch job.

Docker Compose (add under batch profile):
    opensanctions-sync:
      build:
        context: .
        dockerfile: services/opensanctions/Dockerfile
      env_file: .env
      profiles: ["batch"]
      depends_on:
        postgres:
          condition: service_healthy

Cron entry (daily at 04:00):
    0 4 * * * cd /path/to/heimdal && docker compose run --rm opensanctions-sync
"""

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.parsers.opensanctions_ftm import stream_extract

# Re-use persist_batch from the batch load script
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from load_opensanctions import persist_batch, print_db_stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("opensanctions-sync")

DEFAULT_DATA_DIR = os.environ.get(
    "OPENSANCTIONS_DATA_PATH",
    str(PROJECT_ROOT / "data" / "opensanctions"),
)
DOWNLOAD_SCRIPT = PROJECT_ROOT / "scripts" / "download-opensanctions.sh"


def download_dataset(data_dir: str) -> Path:
    """Download the latest OpenSanctions dataset using the existing shell script.

    Returns:
        Path to the downloaded default.json file.
    """
    env = os.environ.copy()
    env["OPENSANCTIONS_DATA_PATH"] = data_dir

    logger.info("Downloading latest OpenSanctions dataset to %s", data_dir)
    result = subprocess.run(
        ["bash", str(DOWNLOAD_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=1800,  # 30 min timeout for large download
    )

    if result.returncode != 0:
        logger.error("Download failed: %s", result.stderr)
        raise RuntimeError(f"Download failed with exit code {result.returncode}: {result.stderr}")

    logger.info("Download output: %s", result.stdout.strip())
    filepath = Path(data_dir) / "default.json"
    if not filepath.exists():
        raise FileNotFoundError(f"Downloaded file not found: {filepath}")

    return filepath


def run_sync(
    db_url: str,
    data_dir: str = DEFAULT_DATA_DIR,
    skip_download: bool = False,
    batch_size: int = 5000,
) -> dict[str, int]:
    """Run the full sync: download + extract + persist.

    Args:
        db_url: PostgreSQL connection URL.
        data_dir: Directory for the OpenSanctions data file.
        skip_download: If True, skip download and use existing file.
        batch_size: Records per persist batch.

    Returns:
        Dict with totals for entities, relationships, vessel_links.
    """
    # Step 1: Download
    if not skip_download:
        filepath = download_dataset(data_dir)
    else:
        filepath = Path(data_dir) / "default.json"
        if not filepath.exists():
            raise FileNotFoundError(f"Data file not found: {filepath}")

    # Step 2: Connect to DB
    url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(url)

    try:
        # Step 3: Stream extract + persist
        start_time = time.monotonic()
        totals = {"entities": 0, "relationships": 0, "vessel_links": 0}

        for batch, stats in stream_extract(filepath, batch_size=batch_size):
            counts = persist_batch(conn, batch)
            for key in totals:
                totals[key] += counts[key]

        elapsed = time.monotonic() - start_time

        # Step 4: Log results
        logger.info(
            "Sync complete in %.1fs: %d entities added/updated, "
            "%d relationships added/updated, %d vessel links added/updated",
            elapsed, totals["entities"], totals["relationships"], totals["vessel_links"],
        )

        return totals

    finally:
        conn.close()


def main():
    load_dotenv()
    import argparse

    parser = argparse.ArgumentParser(description="Daily OpenSanctions sync")
    parser.add_argument("--db-url", type=str, help="Database URL")
    parser.add_argument("--data-dir", type=str, default=DEFAULT_DATA_DIR, help="Data directory")
    parser.add_argument("--skip-download", action="store_true", help="Skip download, use existing file")
    parser.add_argument("--batch-size", type=int, default=5000, help="Batch size for DB writes")
    parser.add_argument("--stats", action="store_true", help="Print DB stats after sync")
    args = parser.parse_args()

    db_url = args.db_url or os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL not set. Use --db-url or set DATABASE_URL env var.")

    totals = run_sync(
        db_url=db_url,
        data_dir=args.data_dir,
        skip_download=args.skip_download,
        batch_size=args.batch_size,
    )

    if args.stats:
        url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = psycopg2.connect(url)
        try:
            print_db_stats(conn)
        finally:
            conn.close()


if __name__ == "__main__":
    main()
