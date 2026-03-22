"""Tests for the GFW SAR detections fetcher.

Tests cover request building, response parsing, upsert behavior,
and empty response handling — all with mocked GFW client and DB.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# Add paths for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from sar_fetcher import (
    SAR_DATASET,
    SAR_ENDPOINT,
    _build_date_range,
    _extract_entries,
    fetch_and_store_sar_detections,
    fetch_sar_detections,
    parse_detection,
)


# ===================================================================
# Sample Data — matches real GFW 4Wings API response structure
# ===================================================================

SAMPLE_AOI = {
    "name": "Norwegian Sea",
    "coordinates": [
        [5.0, 60.0],
        [15.0, 60.0],
        [15.0, 70.0],
        [5.0, 70.0],
    ],
}

# Matched vessel (has MMSI)
SAMPLE_VESSEL_MATCHED = {
    "callsign": "9LS2098",
    "dataset": "public-global-vessel-identity:v4.0",
    "date": "2026-03-05 04:00",
    "detections": 1,
    "entryTimestamp": "2026-03-05T04:40:41Z",
    "exitTimestamp": "2026-03-05T04:40:41Z",
    "firstTransmissionDate": "2024-12-25T11:26:17Z",
    "flag": "SLE",
    "geartype": "OTHER",
    "imo": "9292503",
    "lastTransmissionDate": "2025-06-08T16:44:50Z",
    "mmsi": "667002395",
    "shipName": "BULL",
    "vesselId": "a30abd69a-af79-add7-fc44-2c394b098667",
    "vesselType": "OTHER",
}

# Dark vessel (no MMSI)
SAMPLE_VESSEL_DARK = {
    "dataset": "public-global-vessel-identity:v4.0",
    "date": "2026-03-06 08:00",
    "detections": 1,
    "entryTimestamp": "2026-03-06T08:30:00Z",
    "exitTimestamp": "2026-03-06T08:30:00Z",
    "flag": "",
    "geartype": "",
    "imo": "",
    "mmsi": "",
    "shipName": "",
    "vesselId": "dark-vessel-xyz-456",
    "vesselType": "",
}

# Cargo vessel with full details
SAMPLE_VESSEL_CARGO = {
    "callsign": "V4VE4",
    "dataset": "public-global-vessel-identity:v4.0",
    "date": "2026-03-07 04:00",
    "detections": 1,
    "entryTimestamp": "2026-03-07T16:32:02Z",
    "exitTimestamp": "2026-03-07T22:40:40Z",
    "firstTransmissionDate": "2022-10-14T06:51:26Z",
    "flag": "KNA",
    "geartype": "CARGO",
    "imo": "8918708",
    "lastTransmissionDate": "2026-03-20T23:59:02Z",
    "mmsi": "341639000",
    "shipName": "ASMAR",
    "vesselId": "ec99b591c-cc33-acad-9b1b-d0878489e603",
    "vesselType": "CARGO",
}


def _wrap_api_response(detections: list[dict]) -> dict:
    """Wrap detections in the real 4Wings API response structure."""
    return {
        "total": 1,
        "limit": None,
        "offset": None,
        "nextOffset": None,
        "metadata": {},
        "entries": [
            {"public-global-sar-presence:v4.0": detections}
        ],
    }


def _empty_api_response() -> dict:
    """Empty 4Wings API response."""
    return {
        "total": 0,
        "limit": None,
        "offset": None,
        "nextOffset": None,
        "metadata": {},
        "entries": [],
    }


# ===================================================================
# Extract Entries Tests
# ===================================================================


class TestExtractEntries:
    """Test extraction of detections from nested API response."""

    def test_extracts_from_nested_dataset_key(self):
        """Entries nested under dataset version key are extracted."""
        data = _wrap_api_response([SAMPLE_VESSEL_MATCHED, SAMPLE_VESSEL_DARK])
        entries = _extract_entries(data)
        assert len(entries) == 2

    def test_empty_entries_returns_empty_list(self):
        """Empty entries list returns empty."""
        entries = _extract_entries(_empty_api_response())
        assert entries == []

    def test_handles_different_dataset_versions(self):
        """Works with any sar-presence version string."""
        data = {
            "entries": [
                {"public-global-sar-presence:v5.0": [SAMPLE_VESSEL_MATCHED]}
            ]
        }
        entries = _extract_entries(data)
        assert len(entries) == 1

    def test_ignores_non_sar_keys(self):
        """Keys not starting with the SAR dataset prefix are ignored."""
        data = {
            "entries": [
                {
                    "public-global-sar-presence:v4.0": [SAMPLE_VESSEL_MATCHED],
                    "some-other-dataset:v1.0": [{"unrelated": True}],
                }
            ]
        }
        entries = _extract_entries(data)
        assert len(entries) == 1


# ===================================================================
# Parse Detection Tests
# ===================================================================


class TestParseDetection:
    """Test detection parsing and field mapping."""

    def test_parses_matched_vessel(self):
        """Matched vessel fields are correctly mapped."""
        result = parse_detection(SAMPLE_VESSEL_MATCHED)

        assert result["gfw_detection_id"] == "sar-a30abd69a-af79-add7-fc44-2c394b098667-2026-03-05 04:00"
        assert result["detection_time"] == "2026-03-05T04:40:41Z"
        assert result["is_dark"] is False
        assert result["matched_mmsi"] == 667002395
        assert result["matched_category"] == "other"
        assert result["source"] == "gfw"

    def test_dark_vessel_no_mmsi(self):
        """Vessel without MMSI is marked as dark."""
        result = parse_detection(SAMPLE_VESSEL_DARK)

        assert result["gfw_detection_id"].startswith("sar-dark-vessel-xyz-456")
        assert result["is_dark"] is True
        assert result["matched_mmsi"] is None
        assert result["matched_category"] == "unmatched"

    def test_cargo_vessel_type_mapped(self):
        """Vessel type is used as matched_category."""
        result = parse_detection(SAMPLE_VESSEL_CARGO)

        assert result["matched_mmsi"] == 341639000
        assert result["matched_category"] == "cargo"
        assert result["is_dark"] is False

    def test_uses_entry_timestamp_over_date(self):
        """entryTimestamp is preferred over date for detection_time."""
        result = parse_detection(SAMPLE_VESSEL_CARGO)
        assert result["detection_time"] == "2026-03-07T16:32:02Z"

    def test_missing_vessel_id_returns_none_detection_id(self):
        """Detection with no vesselId returns None for gfw_detection_id."""
        result = parse_detection({"lat": 60.0, "lon": 10.0})
        assert result["gfw_detection_id"] is None

    def test_unavailable_fields_are_none(self):
        """Fields not provided by 4Wings API are None."""
        result = parse_detection(SAMPLE_VESSEL_MATCHED)
        assert result["length_m"] is None
        assert result["width_m"] is None
        assert result["heading_deg"] is None
        assert result["confidence"] is None
        assert result["match_distance_m"] is None
        assert result["matching_score"] is None
        assert result["fishing_score"] is None


# ===================================================================
# Date Range Tests
# ===================================================================


class TestDateRange:
    """Test date range building for API requests."""

    def test_default_lookback_from_settings(self):
        """Default lookback uses settings.gfw.sar_lookback_days."""
        start, end = _build_date_range()
        assert start < end

    def test_custom_lookback_override(self):
        """Custom lookback_days overrides the default."""
        start, end = _build_date_range(lookback_days=3)
        assert len(start) == 10  # YYYY-MM-DD
        assert len(end) == 10


# ===================================================================
# Fetch SAR Detections Tests
# ===================================================================


class TestFetchSarDetections:
    """Test the SAR detection fetching logic."""

    @pytest.mark.asyncio
    async def test_builds_correct_request_with_geojson_key(self):
        """4Wings API request uses 'geojson' key, not 'region'."""
        mock_client = AsyncMock()
        mock_client.post.return_value = _wrap_api_response([SAMPLE_VESSEL_MATCHED])

        await fetch_sar_detections(mock_client, [SAMPLE_AOI], lookback_days=7)

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args

        assert call_args[0][0] == SAR_ENDPOINT

        params = call_args[1].get("params") or call_args.kwargs.get("params", {})
        assert params["datasets[0]"] == SAR_DATASET
        assert "date-range" in params
        assert params["group-by"] == "VESSEL_ID"

        body = call_args[1].get("json_body") or call_args.kwargs.get("json_body", {})
        assert "geojson" in body
        assert "region" not in body
        assert body["geojson"]["type"] == "Polygon"
        assert len(body["geojson"]["coordinates"][0]) == 5  # 4 points + closing

    @pytest.mark.asyncio
    async def test_detections_correctly_parsed_from_nested_response(self):
        """Detections nested under dataset key are correctly extracted and parsed."""
        mock_client = AsyncMock()
        mock_client.post.return_value = _wrap_api_response(
            [SAMPLE_VESSEL_MATCHED, SAMPLE_VESSEL_DARK]
        )

        results = await fetch_sar_detections(mock_client, [SAMPLE_AOI])

        assert len(results) == 2
        assert results[0]["matched_mmsi"] == 667002395
        assert results[0]["is_dark"] is False
        assert results[1]["is_dark"] is True

    @pytest.mark.asyncio
    async def test_empty_response_handled_gracefully(self):
        """Empty API response returns empty list without errors."""
        mock_client = AsyncMock()
        mock_client.post.return_value = _empty_api_response()

        results = await fetch_sar_detections(mock_client, [SAMPLE_AOI])
        assert results == []

    @pytest.mark.asyncio
    async def test_empty_aoi_list_returns_empty(self):
        """No AOIs means no API calls and empty result."""
        mock_client = AsyncMock()
        results = await fetch_sar_detections(mock_client, [])
        assert results == []
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_aoi_without_coordinates_skipped(self):
        """AOI with empty coordinates is skipped."""
        mock_client = AsyncMock()
        results = await fetch_sar_detections(
            mock_client, [{"name": "Empty AOI", "coordinates": []}]
        )
        assert results == []
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_aois_fetched(self):
        """Detections from multiple AOIs are combined."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = [
            _wrap_api_response([SAMPLE_VESSEL_MATCHED]),
            _wrap_api_response([SAMPLE_VESSEL_DARK]),
        ]

        aoi2 = {
            "name": "Barents Sea",
            "coordinates": [[30.0, 70.0], [40.0, 70.0], [40.0, 75.0], [30.0, 75.0]],
        }

        results = await fetch_sar_detections(mock_client, [SAMPLE_AOI, aoi2])

        assert len(results) == 2
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_detections_without_vessel_id_filtered_out(self):
        """Detections that have no vesselId are filtered out."""
        mock_client = AsyncMock()
        mock_client.post.return_value = _wrap_api_response([
            SAMPLE_VESSEL_MATCHED,
            {"lat": 60.0, "lon": 10.0, "date": "2026-03-05"},  # No vesselId
        ])

        results = await fetch_sar_detections(mock_client, [SAMPLE_AOI])

        assert len(results) == 1
        assert results[0]["matched_mmsi"] == 667002395

    @pytest.mark.asyncio
    async def test_api_error_handled_gracefully(self):
        """API errors are caught and logged, returning partial results."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Connection timeout")

        results = await fetch_sar_detections(mock_client, [SAMPLE_AOI])
        assert results == []


# ===================================================================
# Fetch and Store Tests
# ===================================================================


class TestFetchAndStoreSarDetections:
    """Test the combined fetch + upsert flow."""

    @pytest.mark.asyncio
    async def test_upsert_called_with_parsed_detections(self):
        """Parsed detections are passed to bulk_upsert_sar_detections."""
        mock_client = AsyncMock()
        mock_client.post.return_value = _wrap_api_response(
            [SAMPLE_VESSEL_MATCHED, SAMPLE_VESSEL_DARK]
        )
        mock_session = AsyncMock()
        mock_upsert = AsyncMock(return_value=2)

        count = await fetch_and_store_sar_detections(
            mock_client, mock_session, [SAMPLE_AOI], _upsert_fn=mock_upsert
        )

        assert count == 2
        mock_upsert.assert_called_once()
        detections_arg = mock_upsert.call_args[0][1]
        assert len(detections_arg) == 2

    @pytest.mark.asyncio
    async def test_no_upsert_on_empty_results(self):
        """No DB call is made when there are no detections."""
        mock_client = AsyncMock()
        mock_client.post.return_value = _empty_api_response()
        mock_session = AsyncMock()
        mock_upsert = AsyncMock()

        count = await fetch_and_store_sar_detections(
            mock_client, mock_session, [SAMPLE_AOI], _upsert_fn=mock_upsert
        )

        assert count == 0
        mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_upsert_uses_stable_detection_id(self):
        """Detections use vesselId+date composite as gfw_detection_id for upsert."""
        mock_client = AsyncMock()
        mock_client.post.return_value = _wrap_api_response([SAMPLE_VESSEL_MATCHED])
        mock_session = AsyncMock()
        mock_upsert = AsyncMock(return_value=1)

        await fetch_and_store_sar_detections(
            mock_client, mock_session, [SAMPLE_AOI], _upsert_fn=mock_upsert
        )

        detections = mock_upsert.call_args[0][1]
        assert detections[0]["gfw_detection_id"].startswith("sar-")
        assert "a30abd69a" in detections[0]["gfw_detection_id"]
