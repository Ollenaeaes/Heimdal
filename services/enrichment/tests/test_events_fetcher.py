"""Tests for the GFW Events fetcher.

Tests cover request building, event type parsing, encounter/port extraction,
upsert behavior, and error handling — all with mocked GFW client.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# Add paths for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from events_fetcher import (
    EVENT_DATASETS,
    EVENTS_ENDPOINT,
    _build_date_range,
    _extract_encounter_mmsi,
    _extract_port_name,
    fetch_and_store_events,
    fetch_events_for_mmsi,
    fetch_events_for_mmsis,
    parse_event,
)


# ===================================================================
# Sample Data
# ===================================================================

SAMPLE_AIS_DISABLING = {
    "id": "evt-gap-001",
    "type": "gap",
    "vessel": {"ssvid": "273456789"},
    "start": "2026-03-01T10:00:00Z",
    "end": "2026-03-01T22:00:00Z",
    "position": {"lat": 65.5, "lon": 10.2},
}

SAMPLE_ENCOUNTER = {
    "id": "evt-enc-002",
    "type": "encounter",
    "vessel": {"ssvid": "273456789"},
    "start": "2026-03-02T14:00:00Z",
    "end": "2026-03-02T18:00:00Z",
    "position": {"lat": 64.8, "lon": 9.5},
    "encounter": {
        "vessel": {
            "ssvid": "351987654",
            "name": "DARK TRADER",
        },
    },
}

SAMPLE_LOITERING = {
    "id": "evt-loi-003",
    "type": "loitering",
    "vessel": {"ssvid": "273456789"},
    "start": "2026-03-03T06:00:00Z",
    "end": "2026-03-03T18:00:00Z",
    "position": {"lat": 66.0, "lon": 11.0},
}

SAMPLE_PORT_VISIT = {
    "id": "evt-port-004",
    "type": "port_visit",
    "vessel": {"ssvid": "273456789"},
    "start": "2026-03-04T08:00:00Z",
    "end": "2026-03-04T20:00:00Z",
    "position": {"lat": 59.9, "lon": 10.7},
    "port_visit": {
        "intermediateAnchorage": {
            "name": "Oslo",
        },
    },
}

SAMPLE_PORT_VISIT_ALT = {
    "id": "evt-port-005",
    "type": "port_visit",
    "vessel": {"ssvid": "351123456"},
    "start": "2026-03-05T10:00:00Z",
    "end": "2026-03-05T22:00:00Z",
    "position": {"lat": 51.9, "lon": 4.5},
    "portVisit": {
        "port": {
            "name": "Rotterdam",
        },
    },
}


# ===================================================================
# Parse Event Tests
# ===================================================================


class TestParseEvent:
    """Test event parsing and field mapping."""

    def test_parse_ais_disabling(self):
        """AIS_DISABLING (gap) events are correctly parsed."""
        result = parse_event(SAMPLE_AIS_DISABLING)

        assert result is not None
        assert result["gfw_event_id"] == "evt-gap-001"
        assert result["event_type"] == "AIS_DISABLING"
        assert result["mmsi"] == 273456789
        assert result["start_time"] == "2026-03-01T10:00:00Z"
        assert result["end_time"] == "2026-03-01T22:00:00Z"
        assert result["lat"] == 65.5
        assert result["lon"] == 10.2
        assert result["encounter_mmsi"] is None
        assert result["port_name"] is None

    def test_parse_encounter(self):
        """ENCOUNTER events are correctly parsed with encounter_mmsi."""
        result = parse_event(SAMPLE_ENCOUNTER)

        assert result is not None
        assert result["gfw_event_id"] == "evt-enc-002"
        assert result["event_type"] == "ENCOUNTER"
        assert result["mmsi"] == 273456789
        assert result["encounter_mmsi"] == 351987654

    def test_parse_loitering(self):
        """LOITERING events are correctly parsed."""
        result = parse_event(SAMPLE_LOITERING)

        assert result is not None
        assert result["gfw_event_id"] == "evt-loi-003"
        assert result["event_type"] == "LOITERING"
        assert result["mmsi"] == 273456789

    def test_parse_port_visit(self):
        """PORT_VISIT events are correctly parsed with port_name."""
        result = parse_event(SAMPLE_PORT_VISIT)

        assert result is not None
        assert result["gfw_event_id"] == "evt-port-004"
        assert result["event_type"] == "PORT_VISIT"
        assert result["port_name"] == "Oslo"

    def test_parse_port_visit_alternative_keys(self):
        """PORT_VISIT events with alternative key structure (portVisit.port)."""
        result = parse_event(SAMPLE_PORT_VISIT_ALT)

        assert result is not None
        assert result["event_type"] == "PORT_VISIT"
        assert result["port_name"] == "Rotterdam"

    def test_all_four_event_types_parsed(self):
        """All 4 event types (AIS_DISABLING, ENCOUNTER, LOITERING, PORT_VISIT) parse correctly."""
        events = [
            SAMPLE_AIS_DISABLING,
            SAMPLE_ENCOUNTER,
            SAMPLE_LOITERING,
            SAMPLE_PORT_VISIT,
        ]
        results = [parse_event(e) for e in events]
        types = {r["event_type"] for r in results if r is not None}

        assert types == {"AIS_DISABLING", "ENCOUNTER", "LOITERING", "PORT_VISIT"}

    def test_unknown_event_type_returns_none(self):
        """Unknown event types are skipped (return None)."""
        result = parse_event({
            "id": "evt-unknown",
            "type": "FISHING",
            "vessel": {"ssvid": "123456789"},
            "start": "2026-03-01T10:00:00Z",
        })
        assert result is None

    def test_missing_id_returns_none(self):
        """Event without an ID returns None."""
        result = parse_event({
            "type": "gap",
            "vessel": {"ssvid": "123456789"},
        })
        assert result is None

    def test_missing_mmsi_returns_none(self):
        """Event without a vessel MMSI returns None."""
        result = parse_event({
            "id": "evt-no-mmsi",
            "type": "gap",
            "vessel": {},
        })
        assert result is None

    def test_details_contains_full_json(self):
        """Event details field contains the full raw event as JSON string."""
        result = parse_event(SAMPLE_AIS_DISABLING)
        assert result is not None
        details = json.loads(result["details"])
        assert details["id"] == "evt-gap-001"
        assert details["type"] == "gap"


# ===================================================================
# Extract Encounter MMSI Tests
# ===================================================================


class TestExtractEncounterMmsi:
    """Test extraction of encountered vessel MMSI."""

    def test_extract_from_encounter_vessel(self):
        """MMSI extracted from encounter.vessel.ssvid."""
        result = _extract_encounter_mmsi(SAMPLE_ENCOUNTER)
        assert result == 351987654

    def test_extract_from_details(self):
        """MMSI extracted from details.encounter_mmsi."""
        event = {
            "details": {"encounter_mmsi": 987654321},
        }
        result = _extract_encounter_mmsi(event)
        assert result == 987654321

    def test_no_encounter_data_returns_none(self):
        """Returns None when no encounter data present."""
        result = _extract_encounter_mmsi({})
        assert result is None


# ===================================================================
# Extract Port Name Tests
# ===================================================================


class TestExtractPortName:
    """Test extraction of port name from port visit events."""

    def test_extract_from_intermediate_anchorage(self):
        """Port name extracted from port_visit.intermediateAnchorage.name."""
        result = _extract_port_name(SAMPLE_PORT_VISIT)
        assert result == "Oslo"

    def test_extract_from_port_visit_port(self):
        """Port name extracted from portVisit.port.name."""
        result = _extract_port_name(SAMPLE_PORT_VISIT_ALT)
        assert result == "Rotterdam"

    def test_no_port_data_returns_none(self):
        """Returns None when no port data present."""
        result = _extract_port_name({})
        assert result is None


# ===================================================================
# Fetch Events Tests
# ===================================================================


class TestFetchEventsForMmsi:
    """Test the event fetching logic per MMSI."""

    @pytest.mark.asyncio
    async def test_builds_correct_request(self):
        """Events API query includes MMSI, date range, and datasets."""
        mock_client = AsyncMock()
        mock_client.get_all_pages.return_value = [SAMPLE_AIS_DISABLING]

        await fetch_events_for_mmsi(mock_client, 273456789, lookback_days=30)

        mock_client.get_all_pages.assert_called_once()
        call_args = mock_client.get_all_pages.call_args

        # Check endpoint
        assert call_args[0][0] == EVENTS_ENDPOINT

        # Check params
        params = call_args[1].get("params") or call_args.kwargs.get("params", {})
        assert params["vessels[0]"] == "273456789"
        assert "start-date" in params
        assert "end-date" in params

        # Check all datasets are included
        dataset_params = [v for k, v in params.items() if k.startswith("datasets[")]
        assert len(dataset_params) == len(EVENT_DATASETS)

    @pytest.mark.asyncio
    async def test_parses_all_event_types(self):
        """All 4 event types from the API are correctly parsed."""
        mock_client = AsyncMock()
        mock_client.get_all_pages.return_value = [
            SAMPLE_AIS_DISABLING,
            SAMPLE_ENCOUNTER,
            SAMPLE_LOITERING,
            SAMPLE_PORT_VISIT,
        ]

        results = await fetch_events_for_mmsi(mock_client, 273456789)

        assert len(results) == 4
        types = {r["event_type"] for r in results}
        assert types == {"AIS_DISABLING", "ENCOUNTER", "LOITERING", "PORT_VISIT"}

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty_list(self):
        """Empty API response returns empty list."""
        mock_client = AsyncMock()
        mock_client.get_all_pages.return_value = []

        results = await fetch_events_for_mmsi(mock_client, 273456789)
        assert results == []

    @pytest.mark.asyncio
    async def test_api_error_returns_empty_list(self):
        """API errors return empty list instead of raising."""
        mock_client = AsyncMock()
        mock_client.get_all_pages.side_effect = Exception("API error")

        results = await fetch_events_for_mmsi(mock_client, 273456789)
        assert results == []


class TestFetchEventsForMmsis:
    """Test fetching events for multiple MMSIs."""

    @pytest.mark.asyncio
    async def test_fetches_for_all_mmsis(self):
        """Events are fetched for each MMSI and combined."""
        mock_client = AsyncMock()
        mock_client.get_all_pages.side_effect = [
            [SAMPLE_AIS_DISABLING],
            [SAMPLE_ENCOUNTER],
        ]

        results = await fetch_events_for_mmsis(
            mock_client, [273456789, 351123456], lookback_days=30
        )

        assert len(results) == 2
        assert mock_client.get_all_pages.call_count == 2


# ===================================================================
# Fetch and Store Tests
# ===================================================================


class TestFetchAndStoreEvents:
    """Test the combined fetch + upsert flow."""

    @pytest.mark.asyncio
    async def test_upsert_called_with_parsed_events(self):
        """Parsed events are passed to bulk_upsert_gfw_events."""
        mock_client = AsyncMock()
        mock_client.get_all_pages.return_value = [
            SAMPLE_AIS_DISABLING,
            SAMPLE_ENCOUNTER,
        ]
        mock_session = AsyncMock()
        mock_upsert = AsyncMock(return_value=2)

        count = await fetch_and_store_events(
            mock_client, mock_session, [273456789], _upsert_fn=mock_upsert
        )

        assert count == 2
        mock_upsert.assert_called_once()
        events_arg = mock_upsert.call_args[0][1]
        assert len(events_arg) == 2

    @pytest.mark.asyncio
    async def test_no_upsert_on_empty_results(self):
        """No DB call when no events found."""
        mock_client = AsyncMock()
        mock_client.get_all_pages.return_value = []
        mock_session = AsyncMock()
        mock_upsert = AsyncMock()

        count = await fetch_and_store_events(
            mock_client, mock_session, [273456789], _upsert_fn=mock_upsert
        )

        assert count == 0
        mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_upsert_uses_gfw_event_id_as_key(self):
        """Events have gfw_event_id set for dedup in the upsert."""
        mock_client = AsyncMock()
        mock_client.get_all_pages.return_value = [SAMPLE_AIS_DISABLING]
        mock_session = AsyncMock()
        mock_upsert = AsyncMock(return_value=1)

        await fetch_and_store_events(
            mock_client, mock_session, [273456789], _upsert_fn=mock_upsert
        )

        events = mock_upsert.call_args[0][1]
        assert events[0]["gfw_event_id"] == "evt-gap-001"

    @pytest.mark.asyncio
    async def test_encounter_mmsi_extracted_for_encounter_events(self):
        """encounter_mmsi is populated for ENCOUNTER events."""
        mock_client = AsyncMock()
        mock_client.get_all_pages.return_value = [SAMPLE_ENCOUNTER]
        mock_session = AsyncMock()
        mock_upsert = AsyncMock(return_value=1)

        await fetch_and_store_events(
            mock_client, mock_session, [273456789], _upsert_fn=mock_upsert
        )

        events = mock_upsert.call_args[0][1]
        assert events[0]["encounter_mmsi"] == 351987654

    @pytest.mark.asyncio
    async def test_port_name_extracted_for_port_visit_events(self):
        """port_name is populated for PORT_VISIT events."""
        mock_client = AsyncMock()
        mock_client.get_all_pages.return_value = [SAMPLE_PORT_VISIT]
        mock_session = AsyncMock()
        mock_upsert = AsyncMock(return_value=1)

        await fetch_and_store_events(
            mock_client, mock_session, [273456789], _upsert_fn=mock_upsert
        )

        events = mock_upsert.call_args[0][1]
        assert events[0]["port_name"] == "Oslo"
