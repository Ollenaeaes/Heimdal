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
    fetch_and_store_sar_detections,
    fetch_sar_detections,
    parse_detection,
)


# ===================================================================
# Sample Data
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

SAMPLE_DETECTION_RAW = {
    "id": "det-abc-123",
    "timestamp": "2026-03-05T12:00:00Z",
    "lat": 65.5,
    "lon": 10.2,
    "estimatedLength": 85.0,
    "estimatedWidth": 12.0,
    "heading": 180.0,
    "confidence": 0.92,
    "matchedMmsi": 273456789,
    "matchDistance": 500.0,
    "matchingScore": 0.88,
    "fishingScore": 0.15,
}

SAMPLE_DETECTION_DARK = {
    "id": "det-xyz-456",
    "timestamp": "2026-03-06T08:30:00Z",
    "lat": 66.1,
    "lon": 11.5,
    "estimatedLength": 45.0,
    "estimatedWidth": None,
    "heading": 90.0,
    "confidence": 0.78,
    "matchedMmsi": None,
    "matchDistance": None,
    "matchingScore": None,
    "fishingScore": 0.65,
}

SAMPLE_DETECTION_ALT_KEYS = {
    "detectionId": "det-alt-789",
    "date": "2026-03-07T15:00:00Z",
    "latitude": 67.2,
    "longitude": 12.3,
    "length": 120.0,
    "width": 18.0,
    "heading": None,
    "confidence": 0.95,
    "matched_mmsi": 351123456,
    "match_distance": 200.0,
    "matching_score": 0.99,
    "fishing_score": 0.01,
}


# ===================================================================
# Parse Detection Tests
# ===================================================================


class TestParseDetection:
    """Test detection parsing and field mapping."""

    def test_parses_standard_detection(self):
        """Standard detection fields are correctly mapped."""
        result = parse_detection(SAMPLE_DETECTION_RAW)

        assert result["gfw_detection_id"] == "det-abc-123"
        assert result["detection_time"] == "2026-03-05T12:00:00Z"
        assert result["lat"] == 65.5
        assert result["lon"] == 10.2
        assert result["length_m"] == 85.0
        assert result["width_m"] == 12.0
        assert result["heading_deg"] == 180.0
        assert result["confidence"] == 0.92
        assert result["is_dark"] is False
        assert result["matched_mmsi"] == 273456789
        assert result["match_distance_m"] == 500.0
        assert result["source"] == "gfw"
        assert result["matching_score"] == 0.88
        assert result["fishing_score"] == 0.15

    def test_dark_detection_no_mmsi(self):
        """Detection without matched_mmsi is marked as dark."""
        result = parse_detection(SAMPLE_DETECTION_DARK)

        assert result["gfw_detection_id"] == "det-xyz-456"
        assert result["is_dark"] is True
        assert result["matched_mmsi"] is None
        assert result["match_distance_m"] is None
        assert result["matching_score"] is None

    def test_alternative_field_names(self):
        """Alternative GFW field names (detectionId, latitude, etc.) are handled."""
        result = parse_detection(SAMPLE_DETECTION_ALT_KEYS)

        assert result["gfw_detection_id"] == "det-alt-789"
        assert result["detection_time"] == "2026-03-07T15:00:00Z"
        assert result["lat"] == 67.2
        assert result["lon"] == 12.3
        assert result["length_m"] == 120.0
        assert result["is_dark"] is False
        assert result["matched_mmsi"] == 351123456
        assert result["matching_score"] == 0.99

    def test_missing_id_returns_none_gfw_detection_id(self):
        """Detection with no ID field returns None for gfw_detection_id."""
        result = parse_detection({"lat": 60.0, "lon": 10.0})
        assert result["gfw_detection_id"] is None


# ===================================================================
# Date Range Tests
# ===================================================================


class TestDateRange:
    """Test date range building for API requests."""

    def test_default_lookback_from_settings(self):
        """Default lookback uses settings.gfw.sar_lookback_days."""
        start, end = _build_date_range()
        # We can't check exact dates, but start should be before end
        assert start < end

    def test_custom_lookback_override(self):
        """Custom lookback_days overrides the default."""
        start, end = _build_date_range(lookback_days=3)
        # Both should be valid date strings
        assert len(start) == 10  # YYYY-MM-DD
        assert len(end) == 10


# ===================================================================
# Fetch SAR Detections Tests
# ===================================================================


class TestFetchSarDetections:
    """Test the SAR detection fetching logic."""

    @pytest.mark.asyncio
    async def test_builds_correct_request_with_aoi_and_date_range(self):
        """4Wings API query includes AOI geometry and date range."""
        mock_client = AsyncMock()
        mock_client.post.return_value = {"entries": [SAMPLE_DETECTION_RAW]}

        await fetch_sar_detections(mock_client, [SAMPLE_AOI], lookback_days=7)

        # Verify the post was called with correct endpoint
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args

        # Check endpoint
        assert call_args[0][0] == SAR_ENDPOINT

        # Check params contain dataset and date range
        params = call_args[1].get("params") or call_args.kwargs.get("params", {})
        assert params["datasets[0]"] == SAR_DATASET
        assert "date-range" in params

        # Check json_body contains region geometry
        body = call_args[1].get("json_body") or call_args.kwargs.get("json_body", {})
        region = body["region"]
        assert region["type"] == "Polygon"
        assert len(region["coordinates"][0]) == 5  # 4 points + closing point

    @pytest.mark.asyncio
    async def test_detections_correctly_parsed(self):
        """Detections from the API are correctly parsed into SarDetection format."""
        mock_client = AsyncMock()
        mock_client.post.return_value = {
            "entries": [SAMPLE_DETECTION_RAW, SAMPLE_DETECTION_DARK],
        }

        results = await fetch_sar_detections(mock_client, [SAMPLE_AOI])

        assert len(results) == 2
        assert results[0]["gfw_detection_id"] == "det-abc-123"
        assert results[0]["is_dark"] is False
        assert results[1]["gfw_detection_id"] == "det-xyz-456"
        assert results[1]["is_dark"] is True

    @pytest.mark.asyncio
    async def test_empty_response_handled_gracefully(self):
        """Empty API response returns empty list without errors."""
        mock_client = AsyncMock()
        mock_client.post.return_value = {"entries": []}

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
            {"entries": [SAMPLE_DETECTION_RAW]},
            {"entries": [SAMPLE_DETECTION_DARK]},
        ]

        aoi2 = {
            "name": "Barents Sea",
            "coordinates": [[30.0, 70.0], [40.0, 70.0], [40.0, 75.0], [30.0, 75.0]],
        }

        results = await fetch_sar_detections(mock_client, [SAMPLE_AOI, aoi2])

        assert len(results) == 2
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_detections_without_id_filtered_out(self):
        """Detections that have no ID are filtered out."""
        mock_client = AsyncMock()
        mock_client.post.return_value = {
            "entries": [
                SAMPLE_DETECTION_RAW,
                {"lat": 60.0, "lon": 10.0},  # No ID
            ],
        }

        results = await fetch_sar_detections(mock_client, [SAMPLE_AOI])

        assert len(results) == 1
        assert results[0]["gfw_detection_id"] == "det-abc-123"

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
        mock_client.post.return_value = {
            "entries": [SAMPLE_DETECTION_RAW, SAMPLE_DETECTION_DARK],
        }
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
        mock_client.post.return_value = {"entries": []}
        mock_session = AsyncMock()
        mock_upsert = AsyncMock()

        count = await fetch_and_store_sar_detections(
            mock_client, mock_session, [SAMPLE_AOI], _upsert_fn=mock_upsert
        )

        assert count == 0
        mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_upsert_prevents_duplicates(self):
        """Detections use gfw_detection_id as unique key for upsert."""
        mock_client = AsyncMock()
        mock_client.post.return_value = {"entries": [SAMPLE_DETECTION_RAW]}
        mock_session = AsyncMock()
        mock_upsert = AsyncMock(return_value=1)

        await fetch_and_store_sar_detections(
            mock_client, mock_session, [SAMPLE_AOI], _upsert_fn=mock_upsert
        )

        # Verify the detection has gfw_detection_id set
        detections = mock_upsert.call_args[0][1]
        assert detections[0]["gfw_detection_id"] == "det-abc-123"
