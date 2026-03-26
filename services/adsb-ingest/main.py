"""ADS-B ingest service entry point.

Polls adsb.lol for aircraft data across Nordic/Baltic regions.
For each poll cycle:
  1. Classify aircraft (of interest vs civilian)
  2. Persist tracks of aircraft of interest
  3. Feed all NACp observations into interference detector
  4. Persist interference observations and events
"""

from __future__ import annotations

import asyncio
import logging
import time

import asyncpg

from shared.config import settings
from shared.logging import setup_logging

from aircraft_catalog import load_csv, sync_to_db
from interference import InterferenceDetector
from poller import AdsbPoller, POLL_CYCLE_INTERVAL
from writer import AdsbBatchWriter

logger = logging.getLogger("adsb-ingest")


async def main():
    setup_logging("adsb-ingest")
    logger.info("Starting ADS-B ingest service")

    # Load aircraft catalog
    catalog = load_csv()

    # Connect to database
    dsn = settings.database_url.get_secret_value().replace("+asyncpg", "")
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=5)

    # Sync aircraft catalog to DB
    await sync_to_db(pool, catalog)

    # Initialize components
    poller = AdsbPoller()
    writer = AdsbBatchWriter(pool)
    detector = InterferenceDetector()

    await poller.start()
    await writer.start()

    stats = {
        "cycles": 0,
        "total_aircraft": 0,
        "aircraft_of_interest": 0,
        "interference_signals": 0,
    }

    try:
        while True:
            cycle_start = time.monotonic()
            stats["cycles"] += 1

            # Poll all regions
            all_aircraft = await poller.poll_all()
            stats["total_aircraft"] += len(all_aircraft)

            if not all_aircraft:
                logger.debug("No aircraft received this cycle")
                await asyncio.sleep(POLL_CYCLE_INTERVAL)
                continue

            # Classify and process
            aircraft_list = list(all_aircraft.values())

            for ac in aircraft_list:
                hex_code = ac.get("hex", "").lower()

                # Check if aircraft of interest
                aoi = catalog.get(hex_code)
                if aoi:
                    writer.add_position(
                        ac,
                        category=aoi.get("category"),
                        country=aoi.get("country"),
                        role=aoi.get("role"),
                    )
                    stats["aircraft_of_interest"] += 1
                elif ac.get("dbFlags", 0) & 1:
                    # Military flag set in adsb.lol DB but not in our catalog
                    writer.add_position(
                        ac,
                        category="military",
                        country=None,
                        role=None,
                    )
                    stats["aircraft_of_interest"] += 1

            # Feed ALL aircraft (including civilian) into interference detector
            signals = detector.process_aircraft(aircraft_list)

            if signals:
                stats["interference_signals"] += len(signals)
                try:
                    await detector.persist_observations(pool, signals)
                    await detector.persist_events(pool, signals)
                except Exception:
                    logger.exception("Failed to persist interference data")

            # Log stats periodically
            if stats["cycles"] % 30 == 0:
                logger.info(
                    "Stats: cycles=%d total_ac=%d aoi=%d interference_signals=%d",
                    stats["cycles"], stats["total_aircraft"],
                    stats["aircraft_of_interest"], stats["interference_signals"],
                )

            # Wait for next cycle
            elapsed = time.monotonic() - cycle_start
            sleep_time = max(0, POLL_CYCLE_INTERVAL - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("Shutting down")
    except Exception:
        logger.exception("Fatal error in main loop")
    finally:
        await poller.stop()
        await writer.stop()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
