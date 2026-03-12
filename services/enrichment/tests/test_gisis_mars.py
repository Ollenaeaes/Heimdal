"""Tests for GISIS and MARS optional lookup clients.

Tests cover enabled/disabled behavior, graceful failure handling,
rate limiting, and data merge priority (GFW > GISIS/MARS).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Add paths for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from gisis_mars import (
    GISISClient,
    MARSClient,
    merge_gisis_data,
    merge_mars_data,
)


# ===================================================================
# GISIS Client Tests
# ===================================================================


class TestGISISClient:
    """Test the GISIS stub client."""

    @pytest.mark.asyncio
    async def test_disabled_returns_none(self):
        """When disabled, lookup returns None immediately."""
        client = GISISClient(enabled=False)
        result = await client.lookup_vessel(1234567)
        assert result is None

    @pytest.mark.asyncio
    async def test_enabled_returns_none_stub(self):
        """When enabled, stub implementation returns None (no scraping yet)."""
        client = GISISClient(enabled=True)
        result = await client.lookup_vessel(1234567)
        assert result is None

    @pytest.mark.asyncio
    async def test_none_imo_returns_none(self):
        """Lookup with falsy IMO returns None."""
        client = GISISClient(enabled=True)
        result = await client.lookup_vessel(0)
        assert result is None

    @pytest.mark.asyncio
    async def test_failure_does_not_raise(self):
        """GISIS failures are caught and return None."""
        client = GISISClient(enabled=True)

        # Monkey-patch to force an exception after rate limiting
        original = client._wait_for_rate_limit

        async def _force_error():
            await original()
            raise ConnectionError("GISIS unavailable")

        client._wait_for_rate_limit = _force_error
        result = await client.lookup_vessel(9876543)
        assert result is None

    def test_default_disabled(self):
        """Client defaults to disabled."""
        client = GISISClient()
        assert client.enabled is False


# ===================================================================
# MARS Client Tests
# ===================================================================


class TestMARSClient:
    """Test the MARS stub client."""

    @pytest.mark.asyncio
    async def test_disabled_returns_none(self):
        """When disabled, lookup returns None immediately."""
        client = MARSClient(enabled=False)
        result = await client.lookup_vessel(273456789)
        assert result is None

    @pytest.mark.asyncio
    async def test_enabled_returns_none_stub(self):
        """When enabled, stub implementation returns None (no scraping yet)."""
        client = MARSClient(enabled=True)
        result = await client.lookup_vessel(273456789)
        assert result is None

    @pytest.mark.asyncio
    async def test_none_mmsi_returns_none(self):
        """Lookup with falsy MMSI returns None."""
        client = MARSClient(enabled=True)
        result = await client.lookup_vessel(0)
        assert result is None

    @pytest.mark.asyncio
    async def test_failure_does_not_raise(self):
        """MARS failures are caught and return None."""
        client = MARSClient(enabled=True)

        original = client._wait_for_rate_limit

        async def _force_error():
            await original()
            raise ConnectionError("MARS unavailable")

        client._wait_for_rate_limit = _force_error
        result = await client.lookup_vessel(273456789)
        assert result is None

    def test_default_disabled(self):
        """Client defaults to disabled."""
        client = MARSClient()
        assert client.enabled is False


# ===================================================================
# Data Merge Tests — GFW Priority
# ===================================================================


class TestMergeGisisData:
    """Test GISIS data merge with GFW priority."""

    def test_gisis_fills_empty_fields(self):
        """GISIS data fills in fields that are None in profile."""
        profile = {
            "mmsi": 273456789,
            "flag_country": None,
            "ship_name": "NORDIC STAR",
            "call_sign": None,
            "registered_owner": None,
        }
        gisis_data = {
            "flag_country": "NO",
            "ship_name": "NORDIC STAR GISIS",
            "call_sign": "LABC",
            "registered_owner": "Nordic Shipping AS",
        }

        result = merge_gisis_data(profile, gisis_data)

        # flag_country filled from GISIS (was None)
        assert result["flag_country"] == "NO"
        # ship_name kept from profile (GFW priority)
        assert result["ship_name"] == "NORDIC STAR"
        # call_sign filled from GISIS (was None)
        assert result["call_sign"] == "LABC"
        # owner filled from GISIS (was None)
        assert result["registered_owner"] == "Nordic Shipping AS"

    def test_gfw_data_takes_priority(self):
        """Existing (GFW) data is never overwritten by GISIS."""
        profile = {
            "mmsi": 273456789,
            "flag_country": "RU",
            "ship_name": "GFW NAME",
            "call_sign": "XYZQ",
            "registered_owner": "GFW Owner",
        }
        gisis_data = {
            "flag_country": "NO",
            "ship_name": "GISIS NAME",
            "call_sign": "LABC",
            "registered_owner": "GISIS Owner",
        }

        result = merge_gisis_data(profile, gisis_data)

        assert result["flag_country"] == "RU"
        assert result["ship_name"] == "GFW NAME"
        assert result["call_sign"] == "XYZQ"
        assert result["registered_owner"] == "GFW Owner"

    def test_empty_gisis_data_leaves_profile_unchanged(self):
        """Empty GISIS data doesn't change anything."""
        profile = {"mmsi": 273456789, "flag_country": "RU"}
        result = merge_gisis_data(profile, {})
        assert result == profile

    def test_does_not_mutate_original(self):
        """Merge returns a new dict, does not mutate the original."""
        profile = {"mmsi": 273456789, "flag_country": None}
        gisis_data = {"flag_country": "NO"}

        result = merge_gisis_data(profile, gisis_data)

        assert result["flag_country"] == "NO"
        assert profile["flag_country"] is None


class TestMergeMarsData:
    """Test MARS data merge with GFW priority."""

    def test_mars_fills_empty_fields(self):
        """MARS data fills in call_sign and flag when empty."""
        profile = {
            "mmsi": 273456789,
            "call_sign": None,
            "flag_country": None,
        }
        mars_data = {
            "call_sign": "UBCD",
            "flag_country": "RU",
        }

        result = merge_mars_data(profile, mars_data)

        assert result["call_sign"] == "UBCD"
        assert result["flag_country"] == "RU"

    def test_gfw_data_takes_priority(self):
        """Existing data is never overwritten by MARS."""
        profile = {
            "mmsi": 273456789,
            "call_sign": "EXISTING",
            "flag_country": "NO",
        }
        mars_data = {
            "call_sign": "MARS_CS",
            "flag_country": "RU",
        }

        result = merge_mars_data(profile, mars_data)

        assert result["call_sign"] == "EXISTING"
        assert result["flag_country"] == "NO"

    def test_empty_mars_data_leaves_profile_unchanged(self):
        """Empty MARS data doesn't change anything."""
        profile = {"mmsi": 273456789, "call_sign": "ABC"}
        result = merge_mars_data(profile, {})
        assert result == profile

    def test_does_not_mutate_original(self):
        """Merge returns a new dict, does not mutate the original."""
        profile = {"mmsi": 273456789, "call_sign": None}
        mars_data = {"call_sign": "UBCD"}

        result = merge_mars_data(profile, mars_data)

        assert result["call_sign"] == "UBCD"
        assert profile["call_sign"] is None
