"""Tests for the enrichment service runner.

Tests cover vessel querying, enrichment filtering, pipeline execution order,
enrichment timestamp tracking, Redis event publishing, batch processing,
and graceful GISIS/MARS failure handling.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# Add paths for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from runner import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_INTERVAL_SECONDS,
    ENRICHED_KEY,
    ENRICHMENT_CHANNEL,
    enrich_batch,
    get_all_mmsis,
    get_unenriched_mmsis,
    mark_enriched,
    publish_enrichment_complete,
    run_cycle,
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
    """Create a mock async DB session.

    enrich_batch queries the DB for elevated/stale vessels. run_cycle
    queries for vessel profiles with risk_tier. We inspect the SQL
    to return appropriate row shapes.
    """
    session = AsyncMock()

    def _make_result(*args, **kwargs):
        result = MagicMock()
        sql = str(args[0]) if args else ""
        # Extract MMSIs from bound params if available
        params = kwargs.get("parameters") or (args[1] if len(args) > 1 else {})
        bound_mmsis = params.get("mmsis", [273456789]) if isinstance(params, dict) else [273456789]

        if "SELECT mmsi, risk_tier" in sql:
            # run_cycle: get_all_enrichable_mmsis — returns (mmsi, tier)
            result.fetchall.return_value = [(m, "yellow") for m in bound_mmsis]
        elif "SELECT mmsi FROM vessel_profiles" in sql and "risk_tier IN" in sql:
            # enrich_batch step 2: yellow+ vessels for events
            result.fetchall.return_value = [(m,) for m in bound_mmsis]
        elif "enriched_at" in sql:
            # enrich_batch step 3: stale vessels for identity
            result.fetchall.return_value = [(m,) for m in bound_mmsis]
        elif "GROUP BY risk_tier" in sql:
            # _log_enrichment_coverage — return empty to skip logging
            result.fetchall.return_value = []
        elif "SELECT mmsi FROM vessel_profiles" in sql:
            # get_all_mmsis
            result.fetchall.return_value = [(m,) for m in bound_mmsis]
        else:
            result.fetchall.return_value = []
        # For queries using mappings()
        result.mappings.return_value.first.return_value = None
        result.mappings.return_value.all.return_value = []
        return result

    session.execute = AsyncMock(side_effect=_make_result)
    return session


@pytest.fixture
def mock_gfw_client():
    """Create a mock GFW client."""
    return AsyncMock()


# ===================================================================
# get_all_mmsis Tests
# ===================================================================


class TestGetAllMmsis:
    """Test querying all vessel MMSIs from the database."""

    @pytest.mark.asyncio
    async def test_returns_mmsis_from_db(self):
        """Queries vessel_profiles and returns list of MMSIs."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (273456789,),
            (351123456,),
            (211234567,),
        ]
        session.execute.return_value = mock_result

        mmsis = await get_all_mmsis(session)

        assert mmsis == [273456789, 351123456, 211234567]
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_table_returns_empty_list(self):
        """Returns empty list when no vessel profiles exist."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        session.execute.return_value = mock_result

        mmsis = await get_all_mmsis(session)

        assert mmsis == []


# ===================================================================
# get_unenriched_mmsis Tests
# ===================================================================


class TestGetUnenrichedMmsis:
    """Test filtering to vessels needing enrichment."""

    @pytest.mark.asyncio
    async def test_never_enriched_included(self, mock_redis):
        """Vessels with no enrichment timestamp are included."""
        mock_redis.hget.return_value = None

        result = await get_unenriched_mmsis(mock_redis, [273456789, 351123456])

        assert 273456789 in result
        assert 351123456 in result

    @pytest.mark.asyncio
    async def test_recently_enriched_excluded(self, mock_redis):
        """Vessels enriched within the interval are excluded."""
        # Set enrichment time to 1 hour ago (within default 6-hour interval)
        recent_ts = str(datetime.now(timezone.utc).timestamp() - 3600)
        mock_redis.hget.return_value = recent_ts

        result = await get_unenriched_mmsis(mock_redis, [273456789])

        assert result == []

    @pytest.mark.asyncio
    async def test_stale_enriched_included(self, mock_redis):
        """Vessels enriched beyond the interval are included."""
        # Set enrichment time to 7 hours ago (beyond default 6-hour interval)
        stale_ts = str(datetime.now(timezone.utc).timestamp() - 7 * 3600)
        mock_redis.hget.return_value = stale_ts

        result = await get_unenriched_mmsis(mock_redis, [273456789])

        assert result == [273456789]

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self, mock_redis):
        """Empty MMSI list returns empty result."""
        result = await get_unenriched_mmsis(mock_redis, [])
        assert result == []

    @pytest.mark.asyncio
    async def test_invalid_timestamp_treated_as_unenriched(self, mock_redis):
        """Invalid timestamp in Redis is treated as unenriched."""
        mock_redis.hget.return_value = "not-a-number"

        result = await get_unenriched_mmsis(mock_redis, [273456789])

        assert result == [273456789]


# ===================================================================
# mark_enriched Tests
# ===================================================================


class TestMarkEnriched:
    """Test recording enrichment timestamps."""

    @pytest.mark.asyncio
    async def test_sets_timestamp_for_each_mmsi(self, mock_redis):
        """Writes current timestamp to Redis hash for each MMSI."""
        await mark_enriched(mock_redis, [273456789, 351123456])

        assert mock_redis.hset.call_count == 2
        # Check keys
        calls = mock_redis.hset.call_args_list
        assert calls[0][0][0] == ENRICHED_KEY
        assert calls[0][0][1] == "273456789"
        assert calls[1][0][0] == ENRICHED_KEY
        assert calls[1][0][1] == "351123456"


# ===================================================================
# publish_enrichment_complete Tests
# ===================================================================


class TestPublishEnrichmentComplete:
    """Test Redis enrichment_complete event publishing."""

    @pytest.mark.asyncio
    async def test_publishes_correct_payload(self, mock_redis):
        """Event payload contains mmsis, gfw_events_count, sar_detections_count."""
        await publish_enrichment_complete(
            mock_redis,
            mmsis=[273456789, 351123456],
            gfw_events_count=15,
            sar_detections_count=3,
        )

        mock_redis.publish.assert_called_once()
        channel, payload_str = mock_redis.publish.call_args[0]

        assert channel == ENRICHMENT_CHANNEL
        payload = json.loads(payload_str)
        assert payload["mmsis"] == [273456789, 351123456]
        assert payload["gfw_events_count"] == 15
        assert payload["sar_detections_count"] == 3


# ===================================================================
# enrich_batch Tests
# ===================================================================


class TestEnrichBatch:
    """Test the enrichment pipeline for a batch of vessels."""

    @pytest.mark.asyncio
    async def test_pipeline_runs_in_correct_order(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """Pipeline steps execute in order: SAR -> events -> vessel identity."""
        call_order = []

        async def mock_events(*a, **kw):
            call_order.append("events")
            return 5

        async def mock_sar(*a, **kw):
            call_order.append("sar")
            return 2

        async def mock_vessel(*a, **kw):
            call_order.append("vessel")
            return {"mmsi": a[2]}

        result = await enrich_batch(
            [273456789],
            gfw_client=mock_gfw_client,
            session=mock_session,
            redis_client=mock_redis,
            aois=[{"name": "test", "coordinates": [[0, 0], [1, 0], [1, 1], [0, 0]]}],
            _events_fn=mock_events,
            _sar_fn=mock_sar,
            _vessel_fn=mock_vessel,
        )

        assert call_order == ["sar", "events", "vessel"]
        assert result["gfw_events_count"] == 5
        assert result["sar_detections_count"] == 2

    @pytest.mark.asyncio
    async def test_events_failure_does_not_block_pipeline(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """If GFW events fails, SAR and vessel identity still run."""
        call_order = []

        async def mock_events(*a, **kw):
            raise Exception("Events API down")

        async def mock_sar(*a, **kw):
            call_order.append("sar")
            return 0

        async def mock_vessel(*a, **kw):
            call_order.append("vessel")
            return None

        result = await enrich_batch(
            [273456789],
            gfw_client=mock_gfw_client,
            session=mock_session,
            redis_client=mock_redis,
            aois=[{"name": "test", "coordinates": [[0, 0]]}],
            _events_fn=mock_events,
            _sar_fn=mock_sar,
            _vessel_fn=mock_vessel,
        )

        assert "sar" in call_order
        assert "vessel" in call_order
        assert result["gfw_events_count"] == 0

    @pytest.mark.asyncio
    async def test_single_vessel_failure_does_not_stop_batch(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """One vessel failing in vessel identity doesn't stop other vessels."""
        call_count = 0

        async def mock_events(*a, **kw):
            return 0

        async def mock_vessel(client, session, mmsi, **kw):
            nonlocal call_count
            call_count += 1
            if mmsi == 273456789:
                raise Exception("Vessel fetch failed")
            return {"mmsi": mmsi}

        await enrich_batch(
            [273456789, 351123456],
            gfw_client=mock_gfw_client,
            session=mock_session,
            redis_client=mock_redis,
            _events_fn=mock_events,
            _vessel_fn=mock_vessel,
        )

        # Both vessels attempted
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_sar_skipped_without_aois(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """SAR fetching is skipped when no AOIs are provided."""
        sar_called = False

        async def mock_events(*a, **kw):
            return 0

        async def mock_sar(*a, **kw):
            nonlocal sar_called
            sar_called = True
            return 0

        async def mock_vessel(*a, **kw):
            return None

        await enrich_batch(
            [273456789],
            gfw_client=mock_gfw_client,
            session=mock_session,
            redis_client=mock_redis,
            aois=None,  # No AOIs
            _events_fn=mock_events,
            _sar_fn=mock_sar,
            _vessel_fn=mock_vessel,
        )

        assert sar_called is False

    @pytest.mark.asyncio
    async def test_gisis_failure_does_not_block(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """GISIS failures don't block the pipeline."""
        gisis_client = AsyncMock()
        gisis_client.lookup_vessel = AsyncMock(side_effect=Exception("GISIS down"))

        async def mock_events(*a, **kw):
            return 0

        async def mock_vessel(*a, **kw):
            return None

        mock_get_profile = AsyncMock(return_value={"mmsi": 273456789, "imo": 1234567})

        # Should not raise — patch the repository function that gets imported inside enrich_batch
        with patch("shared.db.repositories.get_vessel_profile_by_mmsi", mock_get_profile):
            result = await enrich_batch(
                [273456789],
                gfw_client=mock_gfw_client,
                session=mock_session,
                redis_client=mock_redis,
                gisis_client=gisis_client,
                _events_fn=mock_events,
                _vessel_fn=mock_vessel,
            )

        assert result["gfw_events_count"] == 0

    @pytest.mark.asyncio
    async def test_mars_failure_does_not_block(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """MARS failures don't block the pipeline."""
        mars_client = AsyncMock()
        mars_client.lookup_vessel = AsyncMock(side_effect=Exception("MARS down"))

        async def mock_events(*a, **kw):
            return 0

        async def mock_vessel(*a, **kw):
            return None

        # Should not raise
        result = await enrich_batch(
            [273456789],
            gfw_client=mock_gfw_client,
            session=mock_session,
            redis_client=mock_redis,
            mars_client=mars_client,
            _events_fn=mock_events,
            _vessel_fn=mock_vessel,
        )

        assert result["gfw_events_count"] == 0


# ===================================================================
# run_cycle Tests
# ===================================================================


class TestRunCycle:
    """Test the full enrichment cycle."""

    @pytest.mark.asyncio
    async def test_queries_for_unenriched_vessels(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """Cycle queries DB for vessels and filters by enrichment state."""
        all_vessels = [
            (273456789, "green"),
            (351123456, "green"),
            (211234567, "green"),
        ]

        def _result(*args, **kwargs):
            r = MagicMock()
            sql = str(args[0]) if args else ""
            if "SELECT mmsi, risk_tier" in sql:
                r.fetchall.return_value = all_vessels
            elif "risk_tier IN" in sql:
                # No yellow+ vessels — events should be skipped for green
                r.fetchall.return_value = []
            elif "enriched_at" in sql:
                params = kwargs.get("parameters") or (args[1] if len(args) > 1 else {})
                batch = params.get("mmsis", []) if isinstance(params, dict) else []
                r.fetchall.return_value = [(m,) for m in batch]
            else:
                r.fetchall.return_value = []
            r.mappings.return_value.first.return_value = None
            r.mappings.return_value.all.return_value = []
            return r
        mock_session.execute = AsyncMock(side_effect=_result)

        # MMSI 351123456 was recently enriched
        async def hget_side_effect(key, mmsi_str):
            if mmsi_str == "351123456":
                return str(datetime.now(timezone.utc).timestamp())
            return None

        mock_redis.hget.side_effect = hget_side_effect

        async def mock_events(*a, **kw):
            return 0

        async def mock_sar(*a, **kw):
            return 0

        async def mock_vessel(*a, **kw):
            return None

        result = await run_cycle(
            gfw_client=mock_gfw_client,
            session=mock_session,
            redis_client=mock_redis,
            _events_fn=mock_events,
            _sar_fn=mock_sar,
            _vessel_fn=mock_vessel,
        )

        # 2 vessels should have been enriched (not 351123456)
        assert result["total_vessels"] == 2

    @pytest.mark.asyncio
    async def test_updates_last_enriched_after_enrichment(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """last_enriched_at is updated after enrichment via Redis hash."""
        # mock_session fixture handles all queries — default returns 273456789

        async def mock_events(*a, **kw):
            return 3

        async def mock_vessel(*a, **kw):
            return None

        await run_cycle(
            gfw_client=mock_gfw_client,
            session=mock_session,
            redis_client=mock_redis,
            _events_fn=mock_events,
            _vessel_fn=mock_vessel,
        )

        # Check Redis hset was called for enrichment tracking
        mock_redis.hset.assert_called()
        hset_call = mock_redis.hset.call_args_list[0]
        assert hset_call[0][0] == ENRICHED_KEY
        assert hset_call[0][1] == "273456789"

    @pytest.mark.asyncio
    async def test_publishes_enrichment_complete(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """enrichment_complete event is published to Redis after cycle."""
        # mock_session fixture handles all queries — default returns 273456789

        async def mock_events(*a, **kw):
            return 5

        async def mock_vessel(*a, **kw):
            return None

        await run_cycle(
            gfw_client=mock_gfw_client,
            session=mock_session,
            redis_client=mock_redis,
            _events_fn=mock_events,
            _vessel_fn=mock_vessel,
        )

        mock_redis.publish.assert_called_once()
        channel, payload_str = mock_redis.publish.call_args[0]
        assert channel == ENRICHMENT_CHANNEL
        payload = json.loads(payload_str)
        assert 273456789 in payload["mmsis"]
        assert payload["gfw_events_count"] == 5

    @pytest.mark.asyncio
    async def test_no_vessels_skips_enrichment(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """When no vessels need enrichment, cycle completes with zero counts."""
        def _empty_result(*args, **kwargs):
            r = MagicMock()
            r.fetchall.return_value = []
            r.mappings.return_value.first.return_value = None
            r.mappings.return_value.all.return_value = []
            return r
        mock_session.execute = AsyncMock(side_effect=_empty_result)

        result = await run_cycle(
            gfw_client=mock_gfw_client,
            session=mock_session,
            redis_client=mock_redis,
        )

        assert result["total_vessels"] == 0
        assert result["gfw_events_count"] == 0
        assert result["sar_detections_count"] == 0
        mock_redis.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_batch_processing(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """Vessels are processed in batches of the configured size."""
        # Create 5 yellow vessels with batch size of 2
        test_mmsis = list(range(100000000, 100000005))
        call_idx = [0]

        def _batch_result(*args, **kwargs):
            r = MagicMock()
            sql = str(args[0]) if args else ""
            if "SELECT mmsi, risk_tier" in sql:
                # Initial query: return all 5 as yellow
                r.fetchall.return_value = [(m, "yellow") for m in test_mmsis]
            elif "risk_tier IN" in sql:
                # Events filter: return all queried MMSIs as yellow+
                params = kwargs.get("parameters") or (args[1] if len(args) > 1 else {})
                batch = params.get("mmsis", []) if isinstance(params, dict) else []
                r.fetchall.return_value = [(m,) for m in batch]
            elif "enriched_at" in sql:
                # Stale filter: return all queried as stale
                params = kwargs.get("parameters") or (args[1] if len(args) > 1 else {})
                batch = params.get("mmsis", []) if isinstance(params, dict) else []
                r.fetchall.return_value = [(m,) for m in batch]
            else:
                r.fetchall.return_value = []
            r.mappings.return_value.first.return_value = None
            r.mappings.return_value.all.return_value = []
            return r

        mock_session.execute = AsyncMock(side_effect=_batch_result)

        events_calls = []

        async def mock_events(client, session, batch_mmsis, **kw):
            events_calls.append(list(batch_mmsis))
            return len(batch_mmsis)

        async def mock_vessel(*a, **kw):
            return None

        await run_cycle(
            gfw_client=mock_gfw_client,
            session=mock_session,
            redis_client=mock_redis,
            batch_size=2,
            _events_fn=mock_events,
            _vessel_fn=mock_vessel,
        )

        # Should have 3 batches: [2, 2, 1]
        assert len(events_calls) == 3
        assert len(events_calls[0]) == 2
        assert len(events_calls[1]) == 2
        assert len(events_calls[2]) == 1
