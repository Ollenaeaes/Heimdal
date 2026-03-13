"""Shared helpers for GFW multi-event handling.

Provides temporal deduplication and start_time parsing for GFW-sourced
rules that need to evaluate multiple events.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

# Events of the same type within this window are treated as a single event.
TEMPORAL_DEDUP_WINDOW = timedelta(hours=24)


def parse_start_time(event: dict[str, Any]) -> datetime | None:
    """Extract and normalise *start_time* from a GFW event dict.

    Handles both ``datetime`` objects and ISO-format strings.  Returns
    a timezone-aware UTC datetime, or ``None`` if parsing fails.
    """
    raw = event.get("start_time")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw
    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None
    return None


def dedup_events(
    events: Sequence[dict[str, Any]],
    window: timedelta = TEMPORAL_DEDUP_WINDOW,
) -> list[dict[str, Any]]:
    """Temporally deduplicate a sorted list of GFW events.

    Events must already be sorted by ``start_time`` ascending.
    Within *window*, only the first event is kept (callers score each
    event independently so "more severe" selection happens naturally
    via the rule logic).

    Parameters
    ----------
    events:
        GFW event dicts sorted by start_time.
    window:
        Maximum gap between events to consider them duplicates.

    Returns
    -------
    A deduplicated list of events.
    """
    if not events:
        return []

    result: list[dict[str, Any]] = [events[0]]
    last_time = parse_start_time(events[0])

    for event in events[1:]:
        event_time = parse_start_time(event)
        if event_time is None or last_time is None:
            # Can't compare — keep the event
            result.append(event)
            last_time = event_time
            continue
        if (event_time - last_time) > window:
            result.append(event)
            last_time = event_time
        # else: within window, skip (dedup)

    return result


def filter_already_seen(
    events: Sequence[dict[str, Any]],
    existing_anomalies: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove events whose ``gfw_event_id`` already appears in existing anomalies.

    Checks the ``details.gfw_event_id`` field of each existing anomaly.
    """
    seen_ids: set[str] = set()
    for anomaly in existing_anomalies:
        details = anomaly.get("details") or {}
        if isinstance(details, dict):
            eid = details.get("gfw_event_id")
            if eid:
                seen_ids.add(str(eid))

    return [
        e for e in events
        if str(e.get("gfw_event_id", "")) not in seen_ids
    ]
