"""Tests for the GFW Vessel Identity fetcher.

Tests cover API querying, response parsing, Redis caching,
and vessel profile updates — all with mocked GFW client and Redis.
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

from vessel_fetcher import (
    CACHE_KEY_PREFIX,
    VESSEL_DATASET,
    VESSEL_SEARCH_ENDPOINT,
    _cache_key,
    _safe_float,
    _safe_int,
    fetch_and_update_vessel_profile,
    fetch_vessel_by_imo,
    fetch_vessel_by_mmsi,
    parse_vessel_identity,
)


# ===================================================================
# Sample Data
# ===================================================================

SAMPLE_VESSEL_RESPONSE = {
    "entries": [
        {
            "ssvid": "273456789",
            "selfReportedInfo": [
                {
                    "ssvid": "273456789",
                    "shipname": "VOLGA TRADER",
                    "flag": "RUS",
                    "shiptypeText": "Cargo",
                    "callsign": "UBCD",
                    "length": 110.0,
                    "width": 15.0,
                }
            ],
            "registryInfo": [
                {
                    "imoNumber": "9876543",
                    "shipname": "VOLGA TRADER",
                    "flag": "RUS",
                    "shiptypeText": "General Cargo",
                    "callsign": "UBCD",
                    "owner": "Volga Shipping Co.",
                    "operator": "Volga Maritime",
                    "grossTonnage": 5400,
                    "deadweight": 7200,
                    "builtYear": 2005,
                    "lengthOverallLOA": 112.5,
                    "beam": 15.8,
                }
            ],
            "combinedSourcesInfo": [
                {
                    "shipname": "VOLGA TRADER",
                    "flag": "RUS",
                    "grossTonnage": 5400,
                }
            ],
        }
    ]
}

SAMPLE_VESSEL_MINIMAL = {
    "entries": [
        {
            "ssvid": "351123456",
            "selfReportedInfo": [
                {
                    "ssvid": "351123456",
                    "shipname": "PACIFIC STAR",
                    "flag": "PAN",
                }
            ],
        }
    ]
}

SAMPLE_VESSEL_EMPTY = {"entries": []}


# ===================================================================
# Parse Vessel Identity Tests
# ===================================================================


class TestParseVesselIdentity:
    """Test vessel identity parsing and field mapping."""

    def test_parses_full_vessel_record(self):
        """Full vessel record with registry and self-reported data is parsed."""
        raw = SAMPLE_VESSEL_RESPONSE["entries"][0]
        result = parse_vessel_identity(raw)

        assert result["mmsi"] == 273456789
        assert result["imo"] == 9876543
        assert result["ship_name"] == "VOLGA TRADER"
        assert result["flag_country"] == "RU"  # normalized from "RUS"
        assert result["ship_type_text"] == "General Cargo"  # Registry preferred
        assert result["call_sign"] == "UBCD"
        assert result["gross_tonnage"] == 5400
        assert result["dwt"] == 7200
        assert result["build_year"] == 2005
        assert result["length"] == 112.5  # LOA from registry preferred
        assert result["width"] == 15.8  # Beam from registry preferred
        assert result["registered_owner"] == "Volga Shipping Co."
        assert result["operator"] == "Volga Maritime"

    def test_parses_minimal_vessel_record(self):
        """Minimal vessel record with only self-reported data is parsed."""
        raw = SAMPLE_VESSEL_MINIMAL["entries"][0]
        result = parse_vessel_identity(raw)

        assert result["mmsi"] == 351123456
        assert result["ship_name"] == "PACIFIC STAR"
        assert result["flag_country"] == "PA"  # normalized from "PAN"
        # Missing fields are NOT in the result (filtered out)
        assert "gross_tonnage" not in result
        assert "dwt" not in result
        assert "build_year" not in result

    def test_registry_info_preferred_over_self_reported(self):
        """Registry info takes priority over self-reported data."""
        raw = {
            "selfReportedInfo": [{"shipname": "SELF REPORTED NAME", "flag": "XXX"}],
            "registryInfo": [{"shipname": "REGISTRY NAME", "flag": "NOR"}],
        }
        result = parse_vessel_identity(raw)

        assert result["ship_name"] == "REGISTRY NAME"
        assert result["flag_country"] == "NO"  # normalized from "NOR"

    def test_imo_parsing_with_prefix(self):
        """IMO number with 'IMO' prefix is cleaned."""
        raw = {
            "registryInfo": [{"imoNumber": "IMO1234567"}],
        }
        result = parse_vessel_identity(raw)
        assert result["imo"] == 1234567

    def test_none_values_excluded(self):
        """None values are excluded from the result to let COALESCE work."""
        raw = {"ssvid": "123456789"}
        result = parse_vessel_identity(raw)

        assert result["mmsi"] == 123456789
        # Only mmsi should be in the result
        for key in ["imo", "ship_name", "flag_country", "gross_tonnage"]:
            assert key not in result


# ===================================================================
# Safe Conversion Tests
# ===================================================================


class TestSafeConversions:
    """Test safe type conversion utilities."""

    def test_safe_int_valid(self):
        assert _safe_int(42) == 42
        assert _safe_int("42") == 42
        assert _safe_int(42.9) == 42

    def test_safe_int_invalid(self):
        assert _safe_int(None) is None
        assert _safe_int("not a number") is None
        assert _safe_int("") is None

    def test_safe_float_valid(self):
        assert _safe_float(3.14) == 3.14
        assert _safe_float("3.14") == 3.14
        assert _safe_float(42) == 42.0

    def test_safe_float_invalid(self):
        assert _safe_float(None) is None
        assert _safe_float("not a number") is None


# ===================================================================
# Cache Key Tests
# ===================================================================


class TestCacheKey:
    """Test Redis cache key generation."""

    def test_mmsi_cache_key(self):
        key = _cache_key("273456789", "mmsi")
        assert key == f"{CACHE_KEY_PREFIX}mmsi:273456789"

    def test_imo_cache_key(self):
        key = _cache_key("9876543", "imo")
        assert key == f"{CACHE_KEY_PREFIX}imo:9876543"


# ===================================================================
# Fetch Vessel by MMSI Tests
# ===================================================================


class TestFetchVesselByMmsi:
    """Test vessel fetching by MMSI."""

    @pytest.mark.asyncio
    async def test_queries_api_correctly(self):
        """Vessel API query by MMSI sends correct parameters."""
        mock_client = AsyncMock()
        mock_client.get.return_value = SAMPLE_VESSEL_RESPONSE

        result = await fetch_vessel_by_mmsi(mock_client, 273456789)

        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[0][0] == VESSEL_SEARCH_ENDPOINT
        params = call_args[1].get("params") or call_args.kwargs.get("params", {})
        assert params["query"] == "273456789"
        assert params["datasets[0]"] == VESSEL_DATASET

    @pytest.mark.asyncio
    async def test_returns_parsed_identity(self):
        """API response is parsed into vessel identity dict."""
        mock_client = AsyncMock()
        mock_client.get.return_value = SAMPLE_VESSEL_RESPONSE

        result = await fetch_vessel_by_mmsi(mock_client, 273456789)

        assert result is not None
        assert result["mmsi"] == 273456789
        assert result["ship_name"] == "VOLGA TRADER"
        assert result["registered_owner"] == "Volga Shipping Co."

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        """Returns None when the API has no matching vessel."""
        mock_client = AsyncMock()
        mock_client.get.return_value = SAMPLE_VESSEL_EMPTY

        result = await fetch_vessel_by_mmsi(mock_client, 999999999)
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api_call(self):
        """Cache hit returns cached data without calling the API."""
        mock_client = AsyncMock()
        mock_redis = AsyncMock()
        cached_data = {"mmsi": 273456789, "ship_name": "CACHED VESSEL"}
        mock_redis.get.return_value = json.dumps(cached_data)

        result = await fetch_vessel_by_mmsi(
            mock_client, 273456789, redis_client=mock_redis
        )

        assert result == cached_data
        mock_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_api_and_caches(self):
        """Cache miss calls the API and stores the result."""
        mock_client = AsyncMock()
        mock_client.get.return_value = SAMPLE_VESSEL_RESPONSE
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        result = await fetch_vessel_by_mmsi(
            mock_client, 273456789, redis_client=mock_redis
        )

        assert result is not None
        assert result["mmsi"] == 273456789
        mock_client.get.assert_called_once()
        mock_redis.set.assert_called_once()

        # Verify the cache TTL is set
        set_call = mock_redis.set.call_args
        assert set_call[1].get("ex") is not None
        assert set_call[1]["ex"] > 0

    @pytest.mark.asyncio
    async def test_cache_prevents_redundant_api_calls(self):
        """Second call within TTL uses cache, not API."""
        mock_client = AsyncMock()
        mock_client.get.return_value = SAMPLE_VESSEL_RESPONSE
        mock_redis = AsyncMock()

        # First call: cache miss
        mock_redis.get.return_value = None
        result1 = await fetch_vessel_by_mmsi(
            mock_client, 273456789, redis_client=mock_redis
        )

        # Simulate the value being cached
        mock_redis.get.return_value = json.dumps(result1)

        # Second call: cache hit
        result2 = await fetch_vessel_by_mmsi(
            mock_client, 273456789, redis_client=mock_redis
        )

        # API should only have been called once
        assert mock_client.get.call_count == 1
        assert result2 == result1

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self):
        """API errors return None gracefully."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("API timeout")

        result = await fetch_vessel_by_mmsi(mock_client, 273456789)
        assert result is None


# ===================================================================
# Fetch Vessel by IMO Tests
# ===================================================================


class TestFetchVesselByImo:
    """Test vessel fetching by IMO number."""

    @pytest.mark.asyncio
    async def test_queries_api_by_imo(self):
        """Vessel API query by IMO sends correct parameters."""
        mock_client = AsyncMock()
        mock_client.get.return_value = SAMPLE_VESSEL_RESPONSE

        result = await fetch_vessel_by_imo(mock_client, 9876543)

        call_args = mock_client.get.call_args
        params = call_args[1].get("params") or call_args.kwargs.get("params", {})
        assert params["query"] == "9876543"


# ===================================================================
# Fetch and Update Vessel Profile Tests
# ===================================================================


class TestFetchAndUpdateVesselProfile:
    """Test the combined fetch + profile update flow."""

    @pytest.mark.asyncio
    async def test_updates_vessel_profile_with_gfw_data(self):
        """Vessel profile is upserted with GFW identity data."""
        mock_client = AsyncMock()
        mock_client.get.return_value = SAMPLE_VESSEL_RESPONSE
        mock_session = AsyncMock()
        mock_upsert = AsyncMock()

        result = await fetch_and_update_vessel_profile(
            mock_client, mock_session, 273456789, _upsert_fn=mock_upsert
        )

        assert result is not None
        mock_upsert.assert_called_once()

        # Verify the profile data passed to upsert
        profile_data = mock_upsert.call_args[0][1]
        assert profile_data["mmsi"] == 273456789
        assert profile_data["ship_name"] == "VOLGA TRADER"
        assert profile_data["registered_owner"] == "Volga Shipping Co."
        assert profile_data["gross_tonnage"] == 5400
        assert profile_data["build_year"] == 2005

    @pytest.mark.asyncio
    async def test_fallback_to_imo_search(self):
        """Falls back to IMO search when MMSI returns no results."""
        mock_client = AsyncMock()
        # First call (MMSI) returns empty, second call (IMO) returns data
        mock_client.get.side_effect = [
            SAMPLE_VESSEL_EMPTY,
            SAMPLE_VESSEL_RESPONSE,
        ]
        mock_session = AsyncMock()
        mock_upsert = AsyncMock()

        result = await fetch_and_update_vessel_profile(
            mock_client, mock_session, 273456789, imo=9876543,
            _upsert_fn=mock_upsert
        )

        assert result is not None
        assert mock_client.get.call_count == 2
        mock_upsert.assert_called_once()

        # Verify MMSI is set correctly even from IMO fallback
        profile_data = mock_upsert.call_args[0][1]
        assert profile_data["mmsi"] == 273456789

    @pytest.mark.asyncio
    async def test_no_update_when_not_found(self):
        """No profile update when vessel is not found."""
        mock_client = AsyncMock()
        mock_client.get.return_value = SAMPLE_VESSEL_EMPTY
        mock_session = AsyncMock()
        mock_upsert = AsyncMock()

        result = await fetch_and_update_vessel_profile(
            mock_client, mock_session, 999999999, _upsert_fn=mock_upsert
        )

        assert result is None
        mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_ownership_data_updated_with_extracted_fields(self):
        """Profile upsert includes ownership fields from GFW."""
        mock_client = AsyncMock()
        mock_client.get.return_value = SAMPLE_VESSEL_RESPONSE
        mock_session = AsyncMock()
        mock_upsert = AsyncMock()

        await fetch_and_update_vessel_profile(
            mock_client, mock_session, 273456789, _upsert_fn=mock_upsert
        )

        profile_data = mock_upsert.call_args[0][1]
        # Verify ownership-related fields are populated
        assert profile_data["owner"] == "Volga Shipping Co."
        assert profile_data["operator"] == "Volga Maritime"
        assert profile_data["imo"] == 9876543
        assert profile_data["flag_country"] == "RU"  # normalized from "RUS"
        assert profile_data["length"] == 112.5
        assert profile_data["width"] == 15.8
