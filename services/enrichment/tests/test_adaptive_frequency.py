"""Tests for adaptive enrichment frequency (Story 4, Spec 20).

Tests cover tier-aware enrichment intervals, priority ordering, rate-limited
batch scenarios, and configurable thresholds.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add paths for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from runner import ENRICHED_KEY, get_vessels_needing_enrichment


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


def _make_session_with_vessels(vessels: list[tuple[int, str | None]]) -> AsyncMock:
    """Create a mock session that returns the given (mmsi, risk_tier) rows."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = vessels
    session.execute.return_value = mock_result
    return session


def _hours_ago(hours: float) -> str:
    """Return a timestamp string for N hours ago."""
    return str(datetime.now(timezone.utc).timestamp() - hours * 3600)


# ===================================================================
# Tier-Aware Interval Tests
# ===================================================================


class TestTierAwareIntervals:
    """Test that each risk tier uses its own enrichment interval."""

    @pytest.mark.asyncio
    async def test_green_vessel_4h_ago_not_in_batch(self, mock_redis):
        """Green vessel enriched 4 hours ago is NOT due (6h interval)."""
        session = _make_session_with_vessels([(273456789, "green")])

        async def hget_side_effect(key, mmsi_str):
            return _hours_ago(4)

        mock_redis.hget.side_effect = hget_side_effect

        result = await get_vessels_needing_enrichment(session, mock_redis)

        assert 273456789 not in result

    @pytest.mark.asyncio
    async def test_yellow_vessel_3h_ago_in_batch(self, mock_redis):
        """Yellow vessel enriched 3 hours ago IS due (2h interval)."""
        session = _make_session_with_vessels([(351123456, "yellow")])

        async def hget_side_effect(key, mmsi_str):
            return _hours_ago(3)

        mock_redis.hget.side_effect = hget_side_effect

        result = await get_vessels_needing_enrichment(session, mock_redis)

        assert 351123456 in result

    @pytest.mark.asyncio
    async def test_red_vessel_90min_ago_in_batch(self, mock_redis):
        """Red vessel enriched 90 minutes ago IS due (1h interval)."""
        session = _make_session_with_vessels([(211234567, "red")])

        async def hget_side_effect(key, mmsi_str):
            return _hours_ago(1.5)

        mock_redis.hget.side_effect = hget_side_effect

        result = await get_vessels_needing_enrichment(session, mock_redis)

        assert 211234567 in result

    @pytest.mark.asyncio
    async def test_red_vessel_30min_ago_not_in_batch(self, mock_redis):
        """Red vessel enriched 30 minutes ago is NOT due (1h interval)."""
        session = _make_session_with_vessels([(211234567, "red")])

        async def hget_side_effect(key, mmsi_str):
            return _hours_ago(0.5)

        mock_redis.hget.side_effect = hget_side_effect

        result = await get_vessels_needing_enrichment(session, mock_redis)

        assert 211234567 not in result

    @pytest.mark.asyncio
    async def test_never_enriched_always_included(self, mock_redis):
        """Vessels never enriched are always included regardless of tier."""
        session = _make_session_with_vessels([
            (100000001, "green"),
            (100000002, "yellow"),
            (100000003, "red"),
        ])
        mock_redis.hget.return_value = None

        result = await get_vessels_needing_enrichment(session, mock_redis)

        assert set(result) == {100000001, 100000002, 100000003}

    @pytest.mark.asyncio
    async def test_null_risk_tier_treated_as_green(self, mock_redis):
        """Vessel with NULL risk_tier is treated as green (6h interval)."""
        session = _make_session_with_vessels([(273456789, None)])

        async def hget_side_effect(key, mmsi_str):
            return _hours_ago(4)

        mock_redis.hget.side_effect = hget_side_effect

        result = await get_vessels_needing_enrichment(session, mock_redis)

        # 4h < 6h green interval, so not due
        assert 273456789 not in result

    @pytest.mark.asyncio
    async def test_invalid_timestamp_treated_as_needing_enrichment(self, mock_redis):
        """Invalid Redis timestamp is treated as needing enrichment."""
        session = _make_session_with_vessels([(273456789, "green")])
        mock_redis.hget.return_value = "not-a-number"

        result = await get_vessels_needing_enrichment(session, mock_redis)

        assert 273456789 in result


# ===================================================================
# Priority Ordering Tests
# ===================================================================


class TestBatchOrdering:
    """Test that vessels are ordered by risk tier priority."""

    @pytest.mark.asyncio
    async def test_batch_ordering_red_before_yellow_before_green(self, mock_redis):
        """Batch is ordered: red first, then yellow, then green."""
        session = _make_session_with_vessels([
            (100000001, "green"),
            (100000002, "yellow"),
            (100000003, "red"),
            (100000004, "green"),
            (100000005, "yellow"),
        ])
        mock_redis.hget.return_value = None  # all never enriched

        result = await get_vessels_needing_enrichment(session, mock_redis)

        # Red first
        assert result[0] == 100000003
        # Then yellows
        assert set(result[1:3]) == {100000002, 100000005}
        # Then greens
        assert set(result[3:]) == {100000001, 100000004}

    @pytest.mark.asyncio
    async def test_rate_limited_scenario(self, mock_redis):
        """100 green + 5 yellow + 1 red: red and yellow appear first."""
        green_vessels = [(200000000 + i, "green") for i in range(100)]
        yellow_vessels = [(300000000 + i, "yellow") for i in range(5)]
        red_vessels = [(400000001, "red")]
        all_vessels = green_vessels + yellow_vessels + red_vessels

        session = _make_session_with_vessels(all_vessels)
        mock_redis.hget.return_value = None  # all never enriched

        result = await get_vessels_needing_enrichment(session, mock_redis)

        assert len(result) == 106

        # First vessel must be red
        assert result[0] == 400000001

        # Next 5 must be yellow
        yellow_mmsis = set(m for m, _ in yellow_vessels)
        assert set(result[1:6]) == yellow_mmsis

        # Remaining 100 are green
        green_mmsis = set(m for m, _ in green_vessels)
        assert set(result[6:]) == green_mmsis

    @pytest.mark.asyncio
    async def test_only_due_vessels_in_batch(self, mock_redis):
        """Mixed scenario: only vessels past their tier-specific interval appear."""
        session = _make_session_with_vessels([
            (100000001, "green"),   # enriched 4h ago → NOT due (6h)
            (100000002, "yellow"),  # enriched 3h ago → due (2h)
            (100000003, "red"),     # enriched 30min ago → NOT due (1h)
            (100000004, "red"),     # enriched 2h ago → due (1h)
            (100000005, "green"),   # never enriched → due
        ])

        timestamps = {
            "100000001": _hours_ago(4),
            "100000002": _hours_ago(3),
            "100000003": _hours_ago(0.5),
            "100000004": _hours_ago(2),
            "100000005": None,
        }

        async def hget_side_effect(key, mmsi_str):
            return timestamps.get(mmsi_str)

        mock_redis.hget.side_effect = hget_side_effect

        result = await get_vessels_needing_enrichment(session, mock_redis)

        assert set(result) == {100000002, 100000004, 100000005}
        # Red before yellow before green
        assert result[0] == 100000004  # red, due
        assert result[1] == 100000002  # yellow, due
        assert result[2] == 100000005  # green, never enriched


# ===================================================================
# Configurable Thresholds Tests
# ===================================================================


class TestConfigurableThresholds:
    """Test that frequency thresholds can be customized."""

    @pytest.mark.asyncio
    async def test_custom_green_threshold(self, mock_redis):
        """Custom green_hours=12 makes 8h-old green vessel not due."""
        session = _make_session_with_vessels([(273456789, "green")])

        async def hget_side_effect(key, mmsi_str):
            return _hours_ago(8)

        mock_redis.hget.side_effect = hget_side_effect

        # With default 6h: vessel IS due (8h > 6h)
        result_default = await get_vessels_needing_enrichment(session, mock_redis)
        assert 273456789 in result_default

        # With custom 12h: vessel is NOT due (8h < 12h)
        result_custom = await get_vessels_needing_enrichment(
            session, mock_redis, green_hours=12
        )
        assert 273456789 not in result_custom

    @pytest.mark.asyncio
    async def test_custom_yellow_threshold(self, mock_redis):
        """Custom yellow_hours=4 makes 3h-old yellow vessel not due."""
        session = _make_session_with_vessels([(351123456, "yellow")])

        async def hget_side_effect(key, mmsi_str):
            return _hours_ago(3)

        mock_redis.hget.side_effect = hget_side_effect

        # With default 2h: vessel IS due (3h > 2h)
        result_default = await get_vessels_needing_enrichment(session, mock_redis)
        assert 351123456 in result_default

        # With custom 4h: vessel is NOT due (3h < 4h)
        result_custom = await get_vessels_needing_enrichment(
            session, mock_redis, yellow_hours=4
        )
        assert 351123456 not in result_custom

    @pytest.mark.asyncio
    async def test_custom_red_threshold(self, mock_redis):
        """Custom red_hours=0.5 makes 40min-old red vessel due."""
        session = _make_session_with_vessels([(211234567, "red")])

        async def hget_side_effect(key, mmsi_str):
            return _hours_ago(40 / 60)  # 40 minutes ago

        mock_redis.hget.side_effect = hget_side_effect

        # With default 1h: vessel is NOT due (40min < 1h)
        result_default = await get_vessels_needing_enrichment(session, mock_redis)
        assert 211234567 not in result_default

        # With custom 0.5h (30min): vessel IS due (40min > 30min)
        result_custom = await get_vessels_needing_enrichment(
            session, mock_redis, red_hours=0.5
        )
        assert 211234567 in result_custom

    @pytest.mark.asyncio
    async def test_all_custom_thresholds_together(self, mock_redis):
        """All three thresholds can be customized simultaneously."""
        session = _make_session_with_vessels([
            (100000001, "green"),   # enriched 10h ago
            (100000002, "yellow"),  # enriched 5h ago
            (100000003, "red"),     # enriched 3h ago
        ])

        timestamps = {
            "100000001": _hours_ago(10),
            "100000002": _hours_ago(5),
            "100000003": _hours_ago(3),
        }

        async def hget_side_effect(key, mmsi_str):
            return timestamps.get(mmsi_str)

        mock_redis.hget.side_effect = hget_side_effect

        # With very long intervals, none are due
        result = await get_vessels_needing_enrichment(
            session, mock_redis,
            green_hours=24, yellow_hours=12, red_hours=6,
        )
        assert result == []

        # With very short intervals, all are due
        result = await get_vessels_needing_enrichment(
            session, mock_redis,
            green_hours=1, yellow_hours=1, red_hours=1,
        )
        assert len(result) == 3
