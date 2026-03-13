"""Tests for tier-change triggered enrichment.

Tests cover the debounce logic, tier filtering, single-vessel enrichment,
and the tier-change listener integration.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add paths for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from runner import (
    DEFAULT_DEBOUNCE_HOURS,
    TRIGGER_KEY,
    TRIGGER_TIERS,
    enrich_single_vessel,
    mark_triggered,
    should_trigger_enrichment,
)


# ===================================================================
# Helper Fixtures
# ===================================================================


@pytest.fixture
def mock_redis():
    """Create a mock async Redis client."""
    redis = AsyncMock()
    redis.hget = AsyncMock(return_value=None)
    redis.hset = AsyncMock()
    redis.publish = AsyncMock()
    return redis


@pytest.fixture
def mock_session():
    """Create a mock async DB session."""
    return AsyncMock()


@pytest.fixture
def mock_gfw_client():
    """Create a mock GFW client."""
    return AsyncMock()


# ===================================================================
# should_trigger_enrichment Tests
# ===================================================================


class TestShouldTriggerEnrichment:
    """Test the debounce and tier-filtering logic."""

    @pytest.mark.asyncio
    async def test_green_to_yellow_triggers_enrichment(self, mock_redis):
        """Green -> yellow transition should trigger enrichment."""
        mock_redis.hget.return_value = None  # never triggered before

        result = await should_trigger_enrichment(mock_redis, 273456789, "yellow")

        assert result is True
        mock_redis.hget.assert_called_once_with(TRIGGER_KEY, "273456789")

    @pytest.mark.asyncio
    async def test_yellow_to_red_triggers_enrichment(self, mock_redis):
        """Yellow -> red transition should trigger enrichment."""
        mock_redis.hget.return_value = None

        result = await should_trigger_enrichment(mock_redis, 273456789, "red")

        assert result is True

    @pytest.mark.asyncio
    async def test_yellow_to_green_no_trigger(self, mock_redis):
        """Yellow -> green transition should NOT trigger enrichment."""
        result = await should_trigger_enrichment(mock_redis, 273456789, "green")

        assert result is False
        # Should not even check Redis when tier is not in TRIGGER_TIERS
        mock_redis.hget.assert_not_called()

    @pytest.mark.asyncio
    async def test_debounce_recent(self, mock_redis):
        """Vessel triggered 30 minutes ago should be debounced (skipped)."""
        thirty_min_ago = str(datetime.now(timezone.utc).timestamp() - 30 * 60)
        mock_redis.hget.return_value = thirty_min_ago

        result = await should_trigger_enrichment(mock_redis, 273456789, "yellow")

        assert result is False

    @pytest.mark.asyncio
    async def test_debounce_expired(self, mock_redis):
        """Vessel triggered 2 hours ago should trigger again (debounce expired)."""
        two_hours_ago = str(datetime.now(timezone.utc).timestamp() - 2 * 3600)
        mock_redis.hget.return_value = two_hours_ago

        result = await should_trigger_enrichment(mock_redis, 273456789, "yellow")

        assert result is True

    @pytest.mark.asyncio
    async def test_multiple_rapid_changes_debounce(self, mock_redis):
        """After mark_triggered, an immediate check should be debounced."""
        # First call: never triggered → should trigger
        mock_redis.hget.return_value = None
        result1 = await should_trigger_enrichment(mock_redis, 273456789, "yellow")
        assert result1 is True

        # Simulate mark_triggered by setting the timestamp to now
        await mark_triggered(mock_redis, 273456789)

        # Second call: just triggered → should be debounced
        now_ts = str(datetime.now(timezone.utc).timestamp())
        mock_redis.hget.return_value = now_ts
        result2 = await should_trigger_enrichment(mock_redis, 273456789, "red")
        assert result2 is False

    @pytest.mark.asyncio
    async def test_custom_debounce_hours(self, mock_redis):
        """Custom debounce_hours parameter is respected."""
        # Triggered 90 minutes ago
        ninety_min_ago = str(datetime.now(timezone.utc).timestamp() - 90 * 60)
        mock_redis.hget.return_value = ninety_min_ago

        # With default 1-hour debounce: should trigger (90 min > 60 min)
        result = await should_trigger_enrichment(
            mock_redis, 273456789, "yellow", debounce_hours=1
        )
        assert result is True

        # With 2-hour debounce: should NOT trigger (90 min < 120 min)
        result = await should_trigger_enrichment(
            mock_redis, 273456789, "yellow", debounce_hours=2
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_invalid_timestamp_triggers(self, mock_redis):
        """Invalid timestamp in Redis is treated as never triggered."""
        mock_redis.hget.return_value = "not-a-number"

        result = await should_trigger_enrichment(mock_redis, 273456789, "yellow")

        assert result is True

    @pytest.mark.asyncio
    async def test_trigger_tiers_constant(self):
        """TRIGGER_TIERS contains yellow and red."""
        assert TRIGGER_TIERS == {"yellow", "red"}

    @pytest.mark.asyncio
    async def test_default_debounce_hours_constant(self):
        """DEFAULT_DEBOUNCE_HOURS is 1."""
        assert DEFAULT_DEBOUNCE_HOURS == 1


# ===================================================================
# mark_triggered Tests
# ===================================================================


class TestMarkTriggered:
    """Test recording trigger timestamps."""

    @pytest.mark.asyncio
    async def test_sets_timestamp_in_redis(self, mock_redis):
        """mark_triggered writes current timestamp to Redis hash."""
        await mark_triggered(mock_redis, 273456789)

        mock_redis.hset.assert_called_once()
        args = mock_redis.hset.call_args[0]
        assert args[0] == TRIGGER_KEY
        assert args[1] == "273456789"
        # Timestamp should be a valid float
        ts = float(args[2])
        now = datetime.now(timezone.utc).timestamp()
        assert abs(ts - now) < 5  # within 5 seconds


# ===================================================================
# enrich_single_vessel Tests
# ===================================================================


class TestEnrichSingleVessel:
    """Test single-vessel enrichment triggered by tier change."""

    @pytest.mark.asyncio
    async def test_calls_enrich_batch_with_single_mmsi(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """enrich_single_vessel calls enrich_batch with a single MMSI list."""
        mock_batch_result = {
            "gfw_events_count": 3,
            "sar_detections_count": 1,
            "failed_mmsis": set(),
        }

        with patch("runner.enrich_batch", new_callable=AsyncMock) as mock_enrich:
            mock_enrich.return_value = mock_batch_result

            result = await enrich_single_vessel(
                273456789,
                gfw_client=mock_gfw_client,
                session=mock_session,
                redis_client=mock_redis,
            )

        mock_enrich.assert_called_once()
        call_args = mock_enrich.call_args
        assert call_args[0][0] == [273456789]
        assert result["gfw_events_count"] == 3
        assert result["sar_detections_count"] == 1

    @pytest.mark.asyncio
    async def test_marks_enriched_and_triggered_on_success(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """On success, marks vessel as enriched and records trigger timestamp."""
        mock_batch_result = {
            "gfw_events_count": 2,
            "sar_detections_count": 0,
            "failed_mmsis": set(),
        }

        with patch("runner.enrich_batch", new_callable=AsyncMock) as mock_enrich:
            mock_enrich.return_value = mock_batch_result

            await enrich_single_vessel(
                273456789,
                gfw_client=mock_gfw_client,
                session=mock_session,
                redis_client=mock_redis,
            )

        # Should have called hset for both ENRICHED_KEY and TRIGGER_KEY
        hset_calls = mock_redis.hset.call_args_list
        keys_written = {call[0][0] for call in hset_calls}
        assert "heimdal:enriched" in keys_written
        assert TRIGGER_KEY in keys_written

    @pytest.mark.asyncio
    async def test_publishes_enrichment_complete_on_success(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """On success, publishes enrichment_complete event."""
        mock_batch_result = {
            "gfw_events_count": 5,
            "sar_detections_count": 2,
            "failed_mmsis": set(),
        }

        with patch("runner.enrich_batch", new_callable=AsyncMock) as mock_enrich:
            mock_enrich.return_value = mock_batch_result

            await enrich_single_vessel(
                273456789,
                gfw_client=mock_gfw_client,
                session=mock_session,
                redis_client=mock_redis,
            )

        mock_redis.publish.assert_called_once()
        channel, payload_str = mock_redis.publish.call_args[0]
        assert channel == "heimdal:enrichment_complete"
        payload = json.loads(payload_str)
        assert payload["mmsis"] == [273456789]
        assert payload["gfw_events_count"] == 5
        assert payload["sar_detections_count"] == 2

    @pytest.mark.asyncio
    async def test_does_not_mark_on_failure(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """When the MMSI is in failed_mmsis, do not mark enriched/triggered."""
        mock_batch_result = {
            "gfw_events_count": 0,
            "sar_detections_count": 0,
            "failed_mmsis": {273456789},
        }

        with patch("runner.enrich_batch", new_callable=AsyncMock) as mock_enrich:
            mock_enrich.return_value = mock_batch_result

            await enrich_single_vessel(
                273456789,
                gfw_client=mock_gfw_client,
                session=mock_session,
                redis_client=mock_redis,
            )

        # Should NOT have called hset or publish
        mock_redis.hset.assert_not_called()
        mock_redis.publish.assert_not_called()
