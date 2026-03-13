"""Fetch SAR vessel detections from the GFW 4Wings API.

Queries the 4Wings API for SAR detections within configured AOIs and
lookback window, then upserts results into the sar_detections table.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

sys.path.insert(0, "/app")

from shared.config import settings
from shared.models.sar import SarDetection

logger = logging.getLogger("enrichment.sar_fetcher")

# 4Wings SAR detections endpoint
SAR_ENDPOINT = "/v3/4wings/report"

# GFW dataset for SAR detections
SAR_DATASET = "public-global-sar-presence:latest"

# Event types to filter for vessel detections
SAR_EVENT_TYPE = "detect"


def _build_date_range(lookback_days: int | None = None) -> tuple[str, str]:
    """Build ISO date strings for the lookback window.

    Returns (start_date, end_date) as YYYY-MM-DD strings.
    """
    days = lookback_days if lookback_days is not None else settings.gfw.sar_lookback_days
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _build_spatial_filter(aois: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert AOI configs into GeoJSON features for the 4Wings spatial filter.

    Each AOI should have: name, coordinates (list of [lon, lat] pairs forming a polygon).
    """
    features = []
    for aoi in aois:
        coords = aoi.get("coordinates", [])
        # Ensure the polygon is closed
        if coords and coords[0] != coords[-1]:
            coords = coords + [coords[0]]
        features.append({
            "type": "Feature",
            "properties": {"name": aoi.get("name", "aoi")},
            "geometry": {
                "type": "Polygon",
                "coordinates": [coords],
            },
        })
    return features


def parse_detection(raw: dict[str, Any]) -> dict[str, Any]:
    """Parse a raw GFW SAR detection into the format expected by bulk_upsert_sar_detections.

    Maps GFW API fields to our sar_detections table columns.
    """
    matched_category = raw.get("matchedCategory") or raw.get("matched_category")
    return {
        "gfw_detection_id": raw.get("id") or raw.get("detectionId"),
        "detection_time": raw.get("timestamp") or raw.get("date"),
        "lat": raw.get("lat") or raw.get("latitude"),
        "lon": raw.get("lon") or raw.get("longitude"),
        "length_m": raw.get("estimatedLength") or raw.get("length"),
        "width_m": raw.get("estimatedWidth") or raw.get("width"),
        "heading_deg": raw.get("heading"),
        "confidence": raw.get("confidence"),
        "is_dark": matched_category == "unmatched" if matched_category else not bool(raw.get("matchedMmsi") or raw.get("matched_mmsi")),
        "matched_mmsi": raw.get("matchedMmsi") or raw.get("matched_mmsi"),
        "matched_category": matched_category,
        "match_distance_m": raw.get("matchDistance") or raw.get("match_distance"),
        "source": "gfw",
        "matching_score": raw.get("matchingScore") or raw.get("matching_score"),
        "fishing_score": raw.get("fishingScore") or raw.get("fishing_score"),
    }


async def fetch_sar_detections(
    client: Any,
    aois: list[dict[str, Any]],
    *,
    lookback_days: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch SAR detections from GFW 4Wings API for given AOIs.

    Args:
        client: An initialized GFWClient instance.
        aois: List of AOI dicts, each with 'name' and 'coordinates'.
        lookback_days: Override for settings.gfw.sar_lookback_days.

    Returns:
        List of parsed detection dicts ready for bulk_upsert_sar_detections.
    """
    start_date, end_date = _build_date_range(lookback_days)

    logger.info(
        "Fetching SAR detections for %d AOIs from %s to %s",
        len(aois),
        start_date,
        end_date,
    )

    all_detections: list[dict[str, Any]] = []

    for aoi in aois:
        coords = aoi.get("coordinates", [])
        if not coords:
            logger.warning("Skipping AOI '%s' with no coordinates", aoi.get("name"))
            continue

        # Ensure polygon is closed
        if coords and coords[0] != coords[-1]:
            coords = coords + [coords[0]]

        # Build the spatial region body for the 4Wings report endpoint
        region = {
            "type": "Polygon",
            "coordinates": [coords],
        }

        params = {
            "datasets[0]": SAR_DATASET,
            "date-range": f"{start_date},{end_date}",
            "spatial-resolution": "low",
            "temporal-resolution": "daily",
        }

        try:
            data = await client.post(
                SAR_ENDPOINT,
                params=params,
                json_body={"region": region},
            )

            # The 4Wings API returns detections in an 'entries' key or directly as a list
            entries = data.get("entries", []) if isinstance(data, dict) else data
            if not entries:
                logger.info(
                    "No SAR detections found for AOI '%s' in date range %s to %s",
                    aoi.get("name"),
                    start_date,
                    end_date,
                )
                continue

            parsed = [parse_detection(entry) for entry in entries]
            # Filter out detections without a valid ID
            parsed = [d for d in parsed if d["gfw_detection_id"]]
            all_detections.extend(parsed)

            logger.info(
                "Found %d SAR detections for AOI '%s'",
                len(parsed),
                aoi.get("name"),
            )

        except Exception:
            logger.exception(
                "Error fetching SAR detections for AOI '%s'",
                aoi.get("name"),
            )

    logger.info("Total SAR detections fetched: %d", len(all_detections))
    return all_detections


async def fetch_and_store_sar_detections(
    client: Any,
    session: Any,
    aois: list[dict[str, Any]],
    *,
    lookback_days: int | None = None,
    _upsert_fn: Any = None,
) -> int:
    """Fetch SAR detections and upsert them into the database.

    Args:
        client: An initialized GFWClient instance.
        session: An async SQLAlchemy session.
        aois: List of AOI dicts.
        lookback_days: Override for settings.gfw.sar_lookback_days.
        _upsert_fn: Override for the upsert function (for testing).

    Returns:
        Number of detections upserted.
    """
    if _upsert_fn is None:
        from shared.db.repositories import bulk_upsert_sar_detections
        _upsert_fn = bulk_upsert_sar_detections

    detections = await fetch_sar_detections(client, aois, lookback_days=lookback_days)
    if not detections:
        return 0

    count = await _upsert_fn(session, detections)
    logger.info("Upserted %d SAR detections into database", count)
    return count
