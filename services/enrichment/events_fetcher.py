"""Fetch behavioral events from the GFW Events API.

Queries the Events API for AIS disabling, encounters, loitering, and
port visit events for tracked MMSIs, then upserts into gfw_events table.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

sys.path.insert(0, "/app")

from shared.config import settings

logger = logging.getLogger("enrichment.events_fetcher")

# Events API endpoint
EVENTS_ENDPOINT = "/v3/events"

# GFW datasets for each event type
EVENT_DATASETS = [
    "public-global-gaps-events:latest",
    "public-global-encounters-events:latest",
    "public-global-loitering-events:latest",
    "public-global-port-visits-events:latest",
]

# Event types we care about
EVENT_TYPES = ["AIS_DISABLING", "ENCOUNTER", "LOITERING", "PORT_VISIT"]

# GFW event type string to our enum mapping
GFW_EVENT_TYPE_MAP = {
    "gap": "AIS_DISABLING",
    "encounter": "ENCOUNTER",
    "loitering": "LOITERING",
    "port_visit": "PORT_VISIT",
    # Direct mappings (in case GFW uses our names)
    "AIS_DISABLING": "AIS_DISABLING",
    "ENCOUNTER": "ENCOUNTER",
    "LOITERING": "LOITERING",
    "PORT_VISIT": "PORT_VISIT",
}


def _build_date_range(lookback_days: int | None = None) -> tuple[str, str]:
    """Build ISO date strings for the lookback window."""
    days = lookback_days if lookback_days is not None else settings.gfw.events_lookback_days
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%dT%H:%M:%S.000Z"), end.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _extract_encounter_mmsi(event: dict[str, Any]) -> int | None:
    """Extract the encountered vessel's MMSI from an ENCOUNTER event."""
    # Check encounter sub-object
    encounter = event.get("encounter", {})
    if encounter:
        vessel = encounter.get("vessel", {})
        if vessel:
            ssvid = vessel.get("ssvid")
            if ssvid:
                try:
                    return int(ssvid)
                except (ValueError, TypeError):
                    pass

    # Check in event details / additionalProperties
    details = event.get("details", event.get("additionalProperties", {}))
    if isinstance(details, dict):
        enc_mmsi = details.get("encounter_mmsi") or details.get("encounteredVesselMMSI")
        if enc_mmsi:
            try:
                return int(enc_mmsi)
            except (ValueError, TypeError):
                pass

    return None


def _extract_port_name(event: dict[str, Any]) -> str | None:
    """Extract port name from a PORT_VISIT event."""
    # Check port_visit sub-object
    port_visit = event.get("port_visit", event.get("portVisit", {}))
    if port_visit:
        # intermediateAnchorage has port info
        port = port_visit.get("intermediateAnchorage", {})
        if port:
            name = port.get("name")
            if name:
                return str(name)
        # Also check top-level port field
        port_info = port_visit.get("port", {})
        if port_info:
            name = port_info.get("name")
            if name:
                return str(name)

    # Check in event details
    details = event.get("details", event.get("additionalProperties", {}))
    if isinstance(details, dict):
        return details.get("port_name") or details.get("portName")

    return None


def parse_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a raw GFW event into the format expected by bulk_upsert_gfw_events.

    Returns None if the event type is not one we care about or the event
    has no valid ID.
    """
    gfw_event_id = raw.get("id")
    if not gfw_event_id:
        return None

    # Map event type
    raw_type = raw.get("type", "")
    event_type = GFW_EVENT_TYPE_MAP.get(raw_type)
    if not event_type:
        logger.debug("Skipping unknown event type: %s", raw_type)
        return None

    # Extract vessel MMSI
    vessel = raw.get("vessel", {})
    ssvid = vessel.get("ssvid") if isinstance(vessel, dict) else None
    mmsi = raw.get("mmsi")
    if ssvid:
        try:
            mmsi = int(ssvid)
        except (ValueError, TypeError):
            pass
    if not mmsi:
        logger.debug("Skipping event %s with no MMSI", gfw_event_id)
        return None

    # Extract position
    position = raw.get("position", {})
    lat = position.get("lat") if isinstance(position, dict) else raw.get("lat")
    lon = position.get("lon") if isinstance(position, dict) else raw.get("lon")

    # Build details as full event JSON
    details = json.dumps(raw)

    # Type-specific extraction
    encounter_mmsi = None
    port_name = None
    if event_type == "ENCOUNTER":
        encounter_mmsi = _extract_encounter_mmsi(raw)
    elif event_type == "PORT_VISIT":
        port_name = _extract_port_name(raw)

    return {
        "gfw_event_id": str(gfw_event_id),
        "event_type": event_type,
        "mmsi": int(mmsi),
        "start_time": raw.get("start"),
        "end_time": raw.get("end"),
        "lat": lat,
        "lon": lon,
        "details": details,
        "encounter_mmsi": encounter_mmsi,
        "port_name": port_name,
    }


async def fetch_events_for_mmsi(
    client: Any,
    mmsi: int,
    *,
    lookback_days: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch all GFW events for a single MMSI.

    Args:
        client: An initialized GFWClient instance.
        mmsi: The vessel MMSI to query.
        lookback_days: Override for settings.gfw.events_lookback_days.

    Returns:
        List of parsed event dicts ready for bulk_upsert_gfw_events.
    """
    start_date, end_date = _build_date_range(lookback_days)

    params = {
        "vessels[0]": str(mmsi),
        "start-date": start_date,
        "end-date": end_date,
    }

    # Add dataset filters
    for i, dataset in enumerate(EVENT_DATASETS):
        params[f"datasets[{i}]"] = dataset

    logger.debug("Fetching events for MMSI %d from %s to %s", mmsi, start_date, end_date)

    try:
        raw_events = await client.get_all_pages(
            EVENTS_ENDPOINT,
            params=params,
            results_key="entries",
        )
    except Exception:
        logger.exception("Error fetching events for MMSI %d", mmsi)
        return []

    parsed = []
    for raw in raw_events:
        event = parse_event(raw)
        if event is not None:
            # Override MMSI from our query in case the response has a different format
            if not event.get("mmsi"):
                event["mmsi"] = mmsi
            parsed.append(event)

    logger.debug("Parsed %d events for MMSI %d", len(parsed), mmsi)
    return parsed


async def fetch_events_for_mmsis(
    client: Any,
    mmsis: list[int],
    *,
    lookback_days: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch GFW events for multiple MMSIs.

    Args:
        client: An initialized GFWClient instance.
        mmsis: List of MMSIs to query.
        lookback_days: Override for settings.gfw.events_lookback_days.

    Returns:
        Combined list of parsed events for all MMSIs.
    """
    all_events: list[dict[str, Any]] = []

    logger.info(
        "Fetching events for %d vessels with %d-day lookback",
        len(mmsis),
        lookback_days or settings.gfw.events_lookback_days,
    )

    for mmsi in mmsis:
        events = await fetch_events_for_mmsi(client, mmsi, lookback_days=lookback_days)
        all_events.extend(events)

    logger.info("Total GFW events fetched: %d for %d vessels", len(all_events), len(mmsis))
    return all_events


async def fetch_and_store_events(
    client: Any,
    session: Any,
    mmsis: list[int],
    *,
    lookback_days: int | None = None,
    _upsert_fn: Any = None,
) -> int:
    """Fetch GFW events and upsert them into the database.

    Args:
        client: An initialized GFWClient instance.
        session: An async SQLAlchemy session.
        mmsis: List of MMSIs to query.
        lookback_days: Override for settings.gfw.events_lookback_days.
        _upsert_fn: Override for the upsert function (for testing).

    Returns:
        Number of events upserted.
    """
    if _upsert_fn is None:
        from shared.db.repositories import bulk_upsert_gfw_events
        _upsert_fn = bulk_upsert_gfw_events

    events = await fetch_events_for_mmsis(client, mmsis, lookback_days=lookback_days)
    if not events:
        return 0

    count = await _upsert_fn(session, events)
    logger.info("Upserted %d GFW events into database", count)
    return count
