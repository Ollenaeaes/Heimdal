"""Batch pipeline service — replaces real-time scoring and enrichment.

Runs on a cron schedule (or manually).  Executes 4 sequential stages:

  1. LOAD     — Read unloaded JSONL files, parse, bulk INSERT into DB
  2. SCORE    — For each vessel with new data, run the scoring engine
  3. ENRICH   — Run the enrichment cycle (GFW, sanctions, etc.)
  4. BOOKKEEP — Update last_loaded.json, log stats
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import sys
import time
from pathlib import Path

# Ensure /app is on sys.path for shared imports (Docker) and support
# running from repository root during development
sys.path.insert(0, "/app")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# In Docker, scoring/enrichment/ingest sources are volume-mounted.
# In local dev, they're relative to this file.
_scoring_paths = ["/app/scoring_src", str(Path(__file__).resolve().parent.parent / "scoring")]
_enrichment_paths = ["/app/enrichment_src", str(Path(__file__).resolve().parent.parent / "enrichment")]
_ingest_paths = ["/app/ingest_src", str(Path(__file__).resolve().parent.parent / "ais-ingest")]
for p in _scoring_paths + _enrichment_paths + _ingest_paths:
    if Path(p).is_dir() and p not in sys.path:
        sys.path.insert(0, p)

import asyncpg

from shared.config import settings
from shared.logging import setup_logging

from loader import (
    find_unloaded_files,
    load_positions_to_db,
    mark_files_loaded,
    read_jsonl_file,
)

logger = logging.getLogger("batch-pipeline")


async def stage_load(pool: asyncpg.Pool) -> set[int]:
    """Stage 1: Load unloaded JSONL files into the database.

    Returns set of MMSIs that received new data.
    """
    logger.info("=== STAGE 1: LOAD ===")
    start = time.monotonic()

    # Import the AIS parser
    import parser as ais_parser

    unloaded = find_unloaded_files(settings.raw_storage.base_path)
    if not unloaded:
        logger.info("No new files to load")
        return set()

    all_mmsis: set[int] = set()
    total_positions = 0
    loaded_files: list[str] = []

    batch_size = settings.batch_pipeline.load_batch_size

    for filepath in unloaded:
        logger.info("Loading file: %s", filepath)
        messages = read_jsonl_file(filepath)
        if not messages:
            loaded_files.append(str(filepath))
            continue

        # Process in chunks to avoid memory spikes
        for i in range(0, len(messages), batch_size):
            chunk = messages[i : i + batch_size]
            count, mmsis = await load_positions_to_db(pool, chunk, ais_parser)
            total_positions += count
            all_mmsis.update(mmsis)

        loaded_files.append(str(filepath))

    # Mark files as loaded
    mark_files_loaded(loaded_files)

    elapsed = time.monotonic() - start
    logger.info(
        "LOAD complete: %d files, %d positions, %d vessels in %.1fs",
        len(loaded_files),
        total_positions,
        len(all_mmsis),
        elapsed,
    )
    return all_mmsis


async def stage_score(mmsis: set[int]) -> None:
    """Stage 2: Run scoring engine for vessels with new data."""
    logger.info("=== STAGE 2: SCORE ===")
    start = time.monotonic()

    if not mmsis:
        logger.info("No vessels to score")
        return

    from engine import ScoringEngine

    engine = ScoringEngine()
    logger.info("Scoring %d vessels with %d rules", len(mmsis), len(engine.rules))

    batch_size = settings.batch_pipeline.score_batch_size
    scored = 0
    errors = 0

    mmsi_list = sorted(mmsis)
    for i in range(0, len(mmsi_list), batch_size):
        batch = mmsi_list[i : i + batch_size]
        for mmsi in batch:
            try:
                await engine.evaluate_realtime(mmsi)
                await engine.evaluate_gfw(mmsi)
                scored += 1
            except Exception:
                logger.exception("Scoring failed for MMSI %d", mmsi)
                errors += 1

    elapsed = time.monotonic() - start
    logger.info(
        "SCORE complete: %d scored, %d errors in %.1fs",
        scored,
        errors,
        elapsed,
    )


async def stage_enrich(mmsis: set[int]) -> None:
    """Stage 3: Run enrichment for vessels that need it."""
    logger.info("=== STAGE 3: ENRICH ===")
    start = time.monotonic()

    from gfw_client import GFWClient
    from gisis_mars import GISISClient, MARSClient
    from runner import enrich_batch
    from sanctions_matcher import SanctionsIndex
    from shared.db.connection import get_session

    # Load sanctions index
    sanctions_index = SanctionsIndex()
    count = sanctions_index.load()
    if count > 0:
        logger.info("Sanctions index loaded with %d entries", count)
    else:
        logger.warning("No sanctions data — sanctions matching skipped")
        sanctions_index = None

    # Load AOIs from config
    aois = _load_aois()

    # Determine which vessels need enrichment based on tier and last enrichment time
    session_factory = get_session()
    mmsis_to_enrich = await _get_vessels_needing_enrichment(session_factory)

    if not mmsis_to_enrich:
        logger.info("No vessels need enrichment")
        return

    logger.info("Enriching %d vessels", len(mmsis_to_enrich))

    async with GFWClient() as gfw_client:
        async with session_factory() as session:
            result = await enrich_batch(
                mmsis_to_enrich,
                gfw_client=gfw_client,
                session=session,
                redis_client=None,  # No Redis in batch mode
                sanctions_index=sanctions_index,
                aois=aois,
            )
            await session.commit()

    elapsed = time.monotonic() - start
    logger.info(
        "ENRICH complete: %d vessels, %d GFW events, %d SAR detections in %.1fs",
        len(mmsis_to_enrich),
        result.get("gfw_events_count", 0),
        result.get("sar_detections_count", 0),
        elapsed,
    )


async def _get_vessels_needing_enrichment(session_factory) -> list[int]:
    """Query vessels that need enrichment based on tier-adaptive frequency."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import text

    freq = settings.enrichment.frequency
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        # Get vessels ordered by priority: red first, then yellow, then green
        result = await session.execute(
            text("""
                SELECT mmsi, risk_tier, enriched_at
                FROM vessel_profiles
                WHERE mmsi > 0
                ORDER BY
                    CASE risk_tier
                        WHEN 'red' THEN 1
                        WHEN 'yellow' THEN 2
                        ELSE 3
                    END,
                    enriched_at ASC NULLS FIRST
            """)
        )
        rows = result.fetchall()

    mmsis = []
    for row in rows:
        mmsi, tier, enriched_at = row[0], row[1] or "green", row[2]

        # Determine enrichment interval based on tier
        if tier == "red":
            interval = timedelta(hours=freq.red_hours)
        elif tier == "yellow":
            interval = timedelta(hours=freq.yellow_hours)
        else:
            interval = timedelta(hours=freq.green_hours)

        # Needs enrichment if never enriched or interval has passed
        if enriched_at is None or (now - enriched_at) > interval:
            mmsis.append(mmsi)

    return mmsis


def _load_aois() -> list[dict]:
    """Load AOIs from config.yaml."""
    import yaml

    candidates = [
        Path("/app/config.yaml"),
        Path(__file__).resolve().parent.parent.parent / "config.yaml",
    ]
    for yaml_path in candidates:
        if yaml_path.is_file():
            with open(yaml_path) as f:
                data = yaml.safe_load(f) or {}
            return data.get("gfw", {}).get("aois", [])
    return []


async def run_pipeline() -> None:
    """Execute the full batch pipeline."""
    logger.info("Starting batch pipeline run")
    pipeline_start = time.monotonic()

    dsn = settings.database_url.get_secret_value().replace("+asyncpg", "")
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=5)

    try:
        # Stage 1: Load raw files into DB
        mmsis = await stage_load(pool)

        # Stage 2: Score vessels with new data
        await stage_score(mmsis)

        # Stage 3: Enrich vessels that need it
        await stage_enrich(mmsis)

    finally:
        await pool.close()

    elapsed = time.monotonic() - pipeline_start
    logger.info("Batch pipeline complete in %.1fs", elapsed)


async def main() -> None:
    setup_logging("batch-pipeline")
    await run_pipeline()


if __name__ == "__main__":
    asyncio.run(main())
