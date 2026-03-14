"""Tests for services/scoring/gnss_clustering.py."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.scoring.gnss_clustering import (
    _MIN_EVENTS_FOR_ZONE,
    _CLUSTER_RADIUS_NM,
    _find_clusters,
    cluster_spoofing_events,
)


_BASE_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _event(lat, lon, ts_offset_minutes=0, rule_id="spoof_land_position"):
    """Create a spoofing event dict."""
    return {
        "lat": lat,
        "lon": lon,
        "timestamp": (_BASE_TS + timedelta(minutes=ts_offset_minutes)).isoformat(),
        "rule_id": rule_id,
    }


class TestFindClusters:
    """Test the spatial-temporal clustering logic."""

    def test_single_cluster(self):
        """Events close together in space and time form one cluster."""
        events = [
            _event(50.0, 0.0, 0),
            _event(50.01, 0.01, 10),
            _event(50.02, 0.02, 20),
        ]
        # Parse timestamps
        for e in events:
            e["_parsed_ts"] = datetime.fromisoformat(e["timestamp"])

        clusters = _find_clusters(events)
        assert len(clusters) == 1
        assert len(clusters[0]) == 3

    def test_distant_events_separate_clusters(self):
        """Events far apart form separate clusters."""
        events = [
            _event(50.0, 0.0, 0),
            _event(50.01, 0.01, 10),
            _event(60.0, 20.0, 20),  # Very far away
        ]
        for e in events:
            e["_parsed_ts"] = datetime.fromisoformat(e["timestamp"])

        clusters = _find_clusters(events)
        assert len(clusters) == 2

    def test_events_beyond_time_window_separate(self):
        """Events beyond 1-hour window form separate clusters."""
        events = [
            _event(50.0, 0.0, 0),
            _event(50.01, 0.01, 10),
            _event(50.02, 0.02, 120),  # 2 hours later
        ]
        for e in events:
            e["_parsed_ts"] = datetime.fromisoformat(e["timestamp"])

        clusters = _find_clusters(events)
        assert len(clusters) == 2


class TestClusterSpoofingEvents:
    """Test the main clustering function."""

    @pytest.mark.asyncio
    async def test_fewer_than_3_events_returns_zero(self):
        """Below minimum threshold, no zones should be created."""
        session = AsyncMock()
        events = [_event(50.0, 0.0, 0), _event(50.01, 0.01, 10)]
        result = await cluster_spoofing_events(session, events)
        assert result == 0

    @pytest.mark.asyncio
    async def test_non_spoof_events_filtered(self):
        """Events with non-spoof_ rule_id should be filtered out."""
        session = AsyncMock()
        events = [
            _event(50.0, 0.0, 0, rule_id="ais_gap"),
            _event(50.01, 0.01, 10, rule_id="speed_anomaly"),
            _event(50.02, 0.02, 20, rule_id="sanctions_match"),
        ]
        result = await cluster_spoofing_events(session, events)
        assert result == 0

    @pytest.mark.asyncio
    async def test_events_without_position_filtered(self):
        """Events with None lat/lon should be filtered out."""
        session = AsyncMock()
        events = [
            {"lat": None, "lon": 0.0, "timestamp": _BASE_TS.isoformat(), "rule_id": "spoof_land_position"},
            {"lat": 50.0, "lon": None, "timestamp": _BASE_TS.isoformat(), "rule_id": "spoof_land_position"},
            _event(50.0, 0.0, 0),
        ]
        result = await cluster_spoofing_events(session, events)
        assert result == 0  # Only 1 valid event, below threshold

    @pytest.mark.asyncio
    async def test_three_nearby_events_creates_zone(self):
        """3+ spoofing events within radius and time → creates zone."""
        session = AsyncMock()
        # Mock: no existing zone found
        mock_result = MagicMock()
        mock_result.first.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        events = [
            _event(50.0, 0.0, 0),
            _event(50.01, 0.01, 10),
            _event(50.02, 0.02, 20),
        ]
        result = await cluster_spoofing_events(session, events)
        assert result == 1
        assert session.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_existing_zone_is_refreshed(self):
        """If an existing zone is found nearby, it should be refreshed."""
        session = AsyncMock()
        # First call: return existing zone; Second call: update
        mock_existing = MagicMock()
        mock_existing.first.return_value = (42, 5)  # id=42, affected_count=5
        mock_update = MagicMock()

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_existing
            return mock_update

        session.execute = AsyncMock(side_effect=side_effect)

        events = [
            _event(50.0, 0.0, 0),
            _event(50.01, 0.01, 10),
            _event(50.02, 0.02, 20),
        ]
        result = await cluster_spoofing_events(session, events)
        assert result == 1

    @pytest.mark.asyncio
    async def test_mixed_rule_ids_counted(self):
        """Events from different spoof_* rules should still cluster."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        events = [
            _event(50.0, 0.0, 0, rule_id="spoof_land_position"),
            _event(50.01, 0.01, 10, rule_id="spoof_impossible_speed"),
            _event(50.02, 0.02, 20, rule_id="spoof_frozen_position"),
        ]
        result = await cluster_spoofing_events(session, events)
        assert result == 1

    def test_min_events_constant(self):
        assert _MIN_EVENTS_FOR_ZONE == 3

    def test_cluster_radius_constant(self):
        assert _CLUSTER_RADIUS_NM == 20.0
