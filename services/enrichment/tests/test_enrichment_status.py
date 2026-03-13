"""Tests for enrichment status tracking in vessel profiles.

Tests cover the update_enrichment_status function (JSONB structure, sources list,
data coverage booleans, tier recording), enrich_batch integration with status
updates, and enrichment coverage logging.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

import pytest

# Add paths for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from runner import (
    _log_enrichment_coverage,
    enrich_batch,
    update_enrichment_status,
)


# ===================================================================
# Helper Fixtures
# ===================================================================


@pytest.fixture
def mock_session():
    """Create a mock async DB session."""
    session = AsyncMock()
    return session


@pytest.fixture
def mock_redis():
    """Create a mock async Redis client."""
    redis = AsyncMock()
    redis.hget = AsyncMock(return_value=None)
    redis.hset = AsyncMock()
    redis.publish = AsyncMock()
    return redis


@pytest.fixture
def mock_gfw_client():
    """Create a mock GFW client."""
    return AsyncMock()


# ===================================================================
# update_enrichment_status Tests
# ===================================================================


class TestUpdateEnrichmentStatus:
    """Test the update_enrichment_status function."""

    @pytest.mark.asyncio
    async def test_all_data_found(self, mock_session):
        """When all data types are found, all coverage fields are True."""
        await update_enrichment_status(
            mock_session,
            273456789,
            gfw_events_found=True,
            sar_detections_found=True,
            sanctions_checked=True,
            ownership_found=True,
            classification_found=True,
            insurance_found=True,
            tier_at_enrichment="yellow",
        )

        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        params = call_args[0][1]
        assert params["mmsi"] == 273456789

        status = json.loads(params["status"])
        assert status["data_coverage"]["gfw_events"] is True
        assert status["data_coverage"]["sar_detections"] is True
        assert status["data_coverage"]["sanctions"] is True
        assert status["data_coverage"]["ownership"] is True
        assert status["data_coverage"]["classification"] is True
        assert status["data_coverage"]["insurance"] is True
        assert status["data_coverage"]["port_state_control"] is False  # not yet implemented

    @pytest.mark.asyncio
    async def test_partial_coverage(self, mock_session):
        """When some data types are missing, coverage reflects that."""
        await update_enrichment_status(
            mock_session,
            351123456,
            gfw_events_found=True,
            sar_detections_found=False,
            sanctions_checked=True,
            ownership_found=True,
            classification_found=False,
            insurance_found=False,
            tier_at_enrichment="green",
        )

        params = mock_session.execute.call_args[0][1]
        status = json.loads(params["status"])

        assert status["data_coverage"]["gfw_events"] is True
        assert status["data_coverage"]["sar_detections"] is False
        assert status["data_coverage"]["sanctions"] is True
        assert status["data_coverage"]["ownership"] is True
        assert status["data_coverage"]["classification"] is False
        assert status["data_coverage"]["insurance"] is False

    @pytest.mark.asyncio
    async def test_nothing_found(self, mock_session):
        """When no data is found, all coverage fields are False."""
        await update_enrichment_status(
            mock_session,
            211234567,
        )

        params = mock_session.execute.call_args[0][1]
        status = json.loads(params["status"])

        assert status["data_coverage"]["gfw_events"] is False
        assert status["data_coverage"]["sar_detections"] is False
        assert status["data_coverage"]["sanctions"] is False
        assert status["data_coverage"]["ownership"] is False
        assert status["data_coverage"]["classification"] is False
        assert status["data_coverage"]["insurance"] is False
        assert status["enrichment_sources"] == []

    @pytest.mark.asyncio
    async def test_sources_list_correct(self, mock_session):
        """enrichment_sources lists only the sources that had data."""
        await update_enrichment_status(
            mock_session,
            273456789,
            gfw_events_found=True,
            sar_detections_found=True,
            sanctions_checked=True,
            ownership_found=True,
            classification_found=False,
            insurance_found=False,
        )

        params = mock_session.execute.call_args[0][1]
        status = json.loads(params["status"])

        assert "gfw_events" in status["enrichment_sources"]
        assert "gfw_sar" in status["enrichment_sources"]
        assert "gfw_identity" in status["enrichment_sources"]
        assert "opensanctions" in status["enrichment_sources"]
        assert len(status["enrichment_sources"]) == 4

    @pytest.mark.asyncio
    async def test_sources_list_excludes_missing(self, mock_session):
        """enrichment_sources does not include sources without data."""
        await update_enrichment_status(
            mock_session,
            273456789,
            gfw_events_found=False,
            sar_detections_found=False,
            sanctions_checked=False,
            ownership_found=True,
            classification_found=False,
            insurance_found=False,
        )

        params = mock_session.execute.call_args[0][1]
        status = json.loads(params["status"])

        # Only gfw_identity should be in sources (ownership_found=True)
        assert status["enrichment_sources"] == ["gfw_identity"]

    @pytest.mark.asyncio
    async def test_tier_recorded(self, mock_session):
        """tier_at_enrichment captures the vessel's tier at enrichment time."""
        await update_enrichment_status(
            mock_session,
            273456789,
            tier_at_enrichment="red",
        )

        params = mock_session.execute.call_args[0][1]
        status = json.loads(params["status"])
        assert status["tier_at_enrichment"] == "red"

    @pytest.mark.asyncio
    async def test_tier_defaults_to_green(self, mock_session):
        """tier_at_enrichment defaults to 'green' when not specified."""
        await update_enrichment_status(mock_session, 273456789)

        params = mock_session.execute.call_args[0][1]
        status = json.loads(params["status"])
        assert status["tier_at_enrichment"] == "green"

    @pytest.mark.asyncio
    async def test_last_enriched_is_iso_timestamp(self, mock_session):
        """last_enriched is an ISO 8601 formatted timestamp."""
        await update_enrichment_status(mock_session, 273456789)

        params = mock_session.execute.call_args[0][1]
        status = json.loads(params["status"])

        # Should be parseable as an ISO timestamp
        parsed = datetime.fromisoformat(status["last_enriched"])
        assert parsed.tzinfo is not None  # timezone-aware

    @pytest.mark.asyncio
    async def test_sql_updates_correct_columns(self, mock_session):
        """SQL UPDATE targets enrichment_status and enriched_at columns."""
        await update_enrichment_status(mock_session, 273456789)

        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0].text)
        assert "enrichment_status" in sql_text
        assert "enriched_at" in sql_text
        assert "WHERE mmsi = :mmsi" in sql_text


# ===================================================================
# enrich_batch integration with enrichment status
# ===================================================================


class TestEnrichBatchUpdatesStatus:
    """Test that enrich_batch updates enrichment_status for each vessel."""

    @pytest.mark.asyncio
    async def test_updates_status_for_each_vessel(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """enrich_batch calls update_enrichment_status for each non-failed vessel."""
        async def mock_events(*a, **kw):
            return 5

        async def mock_vessel(*a, **kw):
            return None

        mock_profile = {
            "mmsi": 273456789,
            "risk_tier": "yellow",
            "ownership_data": {"owner": "Test Corp"},
            "classification_data": None,
            "insurance_data": None,
        }

        with patch(
            "runner.update_enrichment_status", new_callable=AsyncMock
        ) as mock_update, patch(
            "shared.db.repositories.get_vessel_profile_by_mmsi",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            await enrich_batch(
                [273456789],
                gfw_client=mock_gfw_client,
                session=mock_session,
                redis_client=mock_redis,
                _events_fn=mock_events,
                _vessel_fn=mock_vessel,
            )

            mock_update.assert_called_once_with(
                mock_session,
                273456789,
                gfw_events_found=True,
                sar_detections_found=False,
                sanctions_checked=False,
                ownership_found=True,
                classification_found=False,
                insurance_found=False,
                tier_at_enrichment="yellow",
            )

    @pytest.mark.asyncio
    async def test_skips_failed_vessels(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """enrich_batch does not update status for vessels that failed sanctions."""
        async def mock_events(*a, **kw):
            return 0

        async def mock_vessel(*a, **kw):
            return None

        # Create a sanctions index that raises for one vessel
        sanctions_index = MagicMock()

        mock_profiles = {
            273456789: {"mmsi": 273456789, "risk_tier": "green", "imo": 1234567,
                        "ship_name": "Test", "ownership_data": None,
                        "classification_data": None, "insurance_data": None},
            351123456: {"mmsi": 351123456, "risk_tier": "green", "imo": 7654321,
                        "ship_name": "Test2", "ownership_data": None,
                        "classification_data": None, "insurance_data": None},
        }

        call_count = 0

        async def mock_get_profile(session, mmsi):
            return mock_profiles.get(mmsi)

        def mock_match(idx, imo=None, mmsi=None, name=None):
            nonlocal call_count
            call_count += 1
            if mmsi == 273456789:
                raise Exception("Sanctions check failed")
            return {"matches": []}

        with patch(
            "runner.update_enrichment_status", new_callable=AsyncMock
        ) as mock_update, patch(
            "shared.db.repositories.get_vessel_profile_by_mmsi",
            side_effect=mock_get_profile,
        ), patch(
            "sanctions_matcher.match_vessel",
            side_effect=mock_match,
        ), patch(
            "shared.db.repositories.update_vessel_sanctions",
            new_callable=AsyncMock,
        ):
            result = await enrich_batch(
                [273456789, 351123456],
                gfw_client=mock_gfw_client,
                session=mock_session,
                redis_client=mock_redis,
                sanctions_index=sanctions_index,
                _events_fn=mock_events,
                _vessel_fn=mock_vessel,
            )

            # 273456789 failed sanctions, should be skipped
            assert 273456789 in result["failed_mmsis"]
            # Only 351123456 should get status update
            update_calls = mock_update.call_args_list
            updated_mmsis = [c[0][1] for c in update_calls]
            assert 273456789 not in updated_mmsis
            assert 351123456 in updated_mmsis

    @pytest.mark.asyncio
    async def test_status_update_failure_does_not_block(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """If update_enrichment_status fails, the batch still returns normally."""
        async def mock_events(*a, **kw):
            return 0

        async def mock_vessel(*a, **kw):
            return None

        with patch(
            "runner.update_enrichment_status",
            new_callable=AsyncMock,
            side_effect=Exception("DB error"),
        ), patch(
            "shared.db.repositories.get_vessel_profile_by_mmsi",
            new_callable=AsyncMock,
            return_value={"mmsi": 273456789, "risk_tier": "green",
                          "ownership_data": None, "classification_data": None,
                          "insurance_data": None},
        ):
            # Should not raise
            result = await enrich_batch(
                [273456789],
                gfw_client=mock_gfw_client,
                session=mock_session,
                redis_client=mock_redis,
                _events_fn=mock_events,
                _vessel_fn=mock_vessel,
            )

            assert result["gfw_events_count"] == 0

    @pytest.mark.asyncio
    async def test_sanctions_checked_when_index_provided(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """sanctions_checked=True when sanctions_index is provided."""
        async def mock_events(*a, **kw):
            return 0

        async def mock_vessel(*a, **kw):
            return None

        sanctions_index = MagicMock()
        mock_profile = {
            "mmsi": 273456789, "risk_tier": "green", "imo": 1234567,
            "ship_name": "Test Vessel",
            "ownership_data": None, "classification_data": None,
            "insurance_data": None,
        }

        with patch(
            "runner.update_enrichment_status", new_callable=AsyncMock
        ) as mock_update, patch(
            "shared.db.repositories.get_vessel_profile_by_mmsi",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ), patch(
            "sanctions_matcher.match_vessel",
            return_value={"matches": []},
        ), patch(
            "shared.db.repositories.update_vessel_sanctions",
            new_callable=AsyncMock,
        ):
            await enrich_batch(
                [273456789],
                gfw_client=mock_gfw_client,
                session=mock_session,
                redis_client=mock_redis,
                sanctions_index=sanctions_index,
                _events_fn=mock_events,
                _vessel_fn=mock_vessel,
            )

            mock_update.assert_called_once()
            kwargs = mock_update.call_args[1]
            assert kwargs["sanctions_checked"] is True

    @pytest.mark.asyncio
    async def test_tier_defaults_when_profile_has_none(
        self, mock_gfw_client, mock_session, mock_redis
    ):
        """tier_at_enrichment defaults to 'green' when profile risk_tier is None."""
        async def mock_events(*a, **kw):
            return 0

        async def mock_vessel(*a, **kw):
            return None

        mock_profile = {
            "mmsi": 273456789, "risk_tier": None,
            "ownership_data": None, "classification_data": None,
            "insurance_data": None,
        }

        with patch(
            "runner.update_enrichment_status", new_callable=AsyncMock
        ) as mock_update, patch(
            "shared.db.repositories.get_vessel_profile_by_mmsi",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            await enrich_batch(
                [273456789],
                gfw_client=mock_gfw_client,
                session=mock_session,
                redis_client=mock_redis,
                _events_fn=mock_events,
                _vessel_fn=mock_vessel,
            )

            kwargs = mock_update.call_args[1]
            assert kwargs["tier_at_enrichment"] == "green"


# ===================================================================
# _log_enrichment_coverage Tests
# ===================================================================


class TestLogEnrichmentCoverage:
    """Test the enrichment coverage logging helper."""

    @pytest.mark.asyncio
    async def test_logs_coverage_stats(self, mock_session, caplog):
        """Logs coverage percentages for yellow and red tiers."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("yellow", 10, 8, 6, 2),  # 80% ownership, 60% classification, 20% insurance
            ("red", 5, 5, 4, 3),      # 100% ownership, 80% classification, 60% insurance
        ]
        mock_session.execute.return_value = mock_result

        import logging
        with caplog.at_level(logging.INFO, logger="enrichment.runner"):
            await _log_enrichment_coverage(mock_session)

        assert "yellow" in caplog.text
        assert "red" in caplog.text
        assert "80%" in caplog.text  # yellow ownership
        assert "100%" in caplog.text  # red ownership

    @pytest.mark.asyncio
    async def test_handles_empty_result(self, mock_session, caplog):
        """No logging when no yellow/red vessels exist."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        import logging
        with caplog.at_level(logging.INFO, logger="enrichment.runner"):
            await _log_enrichment_coverage(mock_session)

        # Should not crash, and no tier-specific messages
        assert "yellow" not in caplog.text
        assert "red" not in caplog.text

    @pytest.mark.asyncio
    async def test_queries_correct_tiers(self, mock_session):
        """SQL query filters for yellow and red tiers only."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        await _log_enrichment_coverage(mock_session)

        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0].text)
        assert "yellow" in sql_text
        assert "red" in sql_text
        assert "enrichment_status" in sql_text
