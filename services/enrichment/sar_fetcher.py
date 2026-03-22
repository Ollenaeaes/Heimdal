"""Fetch SAR vessel detections from the GFW 4Wings API.

Queries the 4Wings API for SAR detections within configured AOIs and
lookback window, then upserts results into the sar_detections table.

Uses group-by=VESSEL_ID to get per-vessel detection records including
MMSI, IMO, ship name, flag, and gear type.
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


def _build_date_range(lookback_days: int | None = None) -> tuple[str, str]:
    """Build ISO date strings for the lookback window.

    Returns (start_date, end_date) as YYYY-MM-DD strings.
    """
    days = lookback_days if lookback_days is not None else settings.gfw.sar_lookback_days
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _extract_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract detection entries from the 4Wings response.

    The API nests results under the dataset version key inside each
    entry, e.g. entries[0]["public-global-sar-presence:v4.0"] = [...].
    This extracts and flattens all nested detection records.
    """
    raw_entries = data.get("entries", [])
    detections: list[dict[str, Any]] = []
    for entry in raw_entries:
        if isinstance(entry, dict):
            for key, records in entry.items():
                if key.startswith("public-global-sar-presence") and isinstance(records, list):
                    detections.extend(records)
    return detections


def parse_detection(raw: dict[str, Any], aoi_name: str = "") -> dict[str, Any]:
    """Parse a raw GFW SAR detection into the format expected by bulk_upsert_sar_detections.

    Maps GFW 4Wings API fields to our sar_detections table columns.
    The API returns per-vessel records with: vesselId, date, detections count,
    lat, lon, mmsi, imo, shipName, flag, geartype, callsign, vesselType.
    """
    mmsi_str = raw.get("mmsi") or ""
    matched_mmsi = int(mmsi_str) if mmsi_str and mmsi_str.isdigit() else None

    # A vessel is "dark" if it has no MMSI (unmatched to AIS)
    is_dark = not bool(matched_mmsi)

    # Build a stable detection ID from vesselId + date + location
    vessel_id = raw.get("vesselId", "")
    date_str = raw.get("date", "")
    lat = raw.get("lat")
    lon = raw.get("lon")
    gfw_detection_id = f"sar-{vessel_id}-{date_str}" if vessel_id else None

    # Determine matched_category from vesselType/geartype
    vessel_type = raw.get("vesselType") or raw.get("geartype") or ""
    matched_category = vessel_type.lower() if vessel_type and not is_dark else ("unmatched" if is_dark else None)

    return {
        "gfw_detection_id": gfw_detection_id,
        "detection_time": raw.get("entryTimestamp") or date_str,
        "lat": lat,
        "lon": lon,
        "length_m": None,
        "width_m": None,
        "heading_deg": None,
        "confidence": None,
        "is_dark": is_dark,
        "matched_mmsi": matched_mmsi,
        "matched_category": matched_category,
        "match_distance_m": None,
        "source": "gfw",
        "matching_score": None,
        "fishing_score": None,
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

        # Build GeoJSON body — the API requires the "geojson" key for raw polygons
        geojson = {
            "type": "Polygon",
            "coordinates": [coords],
        }

        params = {
            "datasets[0]": SAR_DATASET,
            "date-range": f"{start_date},{end_date}",
            "spatial-resolution": "HIGH",
            "temporal-resolution": "HOURLY",
            "format": "JSON",
            "group-by": "VESSEL_ID",
            "spatial-aggregation": "true",
        }

        try:
            data = await client.post(
                SAR_ENDPOINT,
                params=params,
                json_body={"geojson": geojson},
            )

            entries = _extract_entries(data)
            if not entries:
                logger.info(
                    "No SAR detections found for AOI '%s' in date range %s to %s",
                    aoi.get("name"),
                    start_date,
                    end_date,
                )
                continue

            aoi_name = aoi.get("name", "")
            parsed = [parse_detection(entry, aoi_name) for entry in entries]
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
