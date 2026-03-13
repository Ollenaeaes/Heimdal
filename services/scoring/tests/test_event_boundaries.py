"""Tests for event boundary detection (check_event_ended) in realtime rules.

Story 3 of spec 17 (event-scoring-model).
All database interactions are mocked — no running services needed.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

# Make imports work
_scoring_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scoring_dir))
sys.path.insert(0, str(_scoring_dir.parent.parent))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 13, 12, 0, 0, tzinfo=timezone.utc)


def _ts(hours_ago: float = 0) -> datetime:
    """Return a timezone-aware datetime *hours_ago* before _NOW."""
    return _NOW - timedelta(hours=hours_ago)


def _pos(
    hours_ago: float = 0,
    lat: float = 55.0,
    lon: float = 20.0,
    sog: float = 10.0,
    cog: float = 180.0,
    nav_status: int = 0,
    draught: float | None = None,
) -> dict[str, Any]:
    """Build a position dict."""
    p: dict[str, Any] = {
        "timestamp": _ts(hours_ago),
        "lat": lat,
        "lon": lon,
        "sog": sog,
        "cog": cog,
        "nav_status": nav_status,
    }
    if draught is not None:
        p["draught"] = draught
    return p


# ===================================================================
# Base class default
# ===================================================================


class TestBaseClassDefault:
    """The default check_event_ended returns False."""

    @pytest.mark.asyncio
    async def test_default_returns_false(self):
        from rules.base import ScoringRule

        # Create a minimal concrete subclass
        class DummyRule(ScoringRule):
            @property
            def rule_id(self) -> str:
                return "dummy"

            @property
            def rule_category(self) -> str:
                return "realtime"

            async def evaluate(self, mmsi, profile, recent_positions, existing_anomalies, gfw_events):
                return None

        rule = DummyRule()
        result = await rule.check_event_ended(
            mmsi=123456789,
            profile=None,
            recent_positions=[],
            active_anomaly={"rule_id": "dummy", "event_start": _NOW.isoformat()},
        )
        assert result is False


# ===================================================================
# Speed Anomaly event boundary
# ===================================================================


class TestSpeedAnomalyEventEnd:
    """Tests for SpeedAnomalyRule.check_event_ended."""

    @pytest.fixture
    def rule(self):
        from rules.speed_anomaly import SpeedAnomalyRule
        return SpeedAnomalyRule()

    @pytest.mark.asyncio
    async def test_vessel_speeds_up_for_30_min_ends_event(self, rule):
        """SOG > 8 knots sustained for 30+ minutes → event ended."""
        # Positions over the last hour, all fast
        positions = [
            _pos(hours_ago=1.0, sog=12.0),
            _pos(hours_ago=0.75, sog=11.0),
            _pos(hours_ago=0.5, sog=10.0),
            _pos(hours_ago=0.25, sog=12.0),
            _pos(hours_ago=0.0, sog=11.5),
        ]
        anomaly = {"rule_id": "speed_anomaly", "event_start": _ts(3.0).isoformat()}
        result = await rule.check_event_ended(123456789, None, positions, anomaly)
        assert result is True

    @pytest.mark.asyncio
    async def test_vessel_still_slow_does_not_end(self, rule):
        """Vessel stays slow → event NOT ended."""
        positions = [
            _pos(hours_ago=1.0, sog=3.0),
            _pos(hours_ago=0.5, sog=2.5),
            _pos(hours_ago=0.0, sog=4.0),
        ]
        anomaly = {"rule_id": "speed_anomaly", "event_start": _ts(3.0).isoformat()}
        result = await rule.check_event_ended(123456789, None, positions, anomaly)
        assert result is False

    @pytest.mark.asyncio
    async def test_mixed_speeds_does_not_end(self, rule):
        """Some fast, some slow → event NOT ended (not sustained)."""
        positions = [
            _pos(hours_ago=1.0, sog=12.0),
            _pos(hours_ago=0.5, sog=5.0),  # slow
            _pos(hours_ago=0.0, sog=12.0),
        ]
        anomaly = {"rule_id": "speed_anomaly", "event_start": _ts(3.0).isoformat()}
        result = await rule.check_event_ended(123456789, None, positions, anomaly)
        assert result is False

    @pytest.mark.asyncio
    async def test_insufficient_positions(self, rule):
        """Less than 2 positions → cannot determine, returns False."""
        positions = [_pos(hours_ago=0.0, sog=12.0)]
        anomaly = {"rule_id": "speed_anomaly", "event_start": _ts(3.0).isoformat()}
        result = await rule.check_event_ended(123456789, None, positions, anomaly)
        assert result is False

    @pytest.mark.asyncio
    async def test_fast_but_under_30_min_does_not_end(self, rule):
        """All fast but duration < 30 min → event NOT ended."""
        positions = [
            _pos(hours_ago=0.3, sog=12.0),  # ~18 min ago
            _pos(hours_ago=0.0, sog=11.0),
        ]
        anomaly = {"rule_id": "speed_anomaly", "event_start": _ts(3.0).isoformat()}
        result = await rule.check_event_ended(123456789, None, positions, anomaly)
        assert result is False


# ===================================================================
# STS Proximity event boundary
# ===================================================================


class TestStsProximityEventEnd:
    """Tests for StsProximityRule.check_event_ended."""

    @pytest.fixture
    def rule(self):
        from rules.sts_proximity import StsProximityRule
        return StsProximityRule()

    @pytest.mark.asyncio
    async def test_vessel_departs_zone_ends_event(self, rule):
        """Vessel leaves STS zone → event ended."""
        positions = [_pos(hours_ago=0.0, lat=60.0, lon=25.0)]
        anomaly = {"rule_id": "sts_proximity", "event_start": _ts(6.0).isoformat()}

        with patch(
            "rules.sts_proximity._check_sts_zone_db",
            new_callable=AsyncMock,
            return_value=None,  # Not in any zone
        ):
            result = await rule.check_event_ended(123456789, None, positions, anomaly)
        assert result is True

    @pytest.mark.asyncio
    async def test_vessel_still_in_zone_does_not_end(self, rule):
        """Vessel still in STS zone → event NOT ended."""
        positions = [_pos(hours_ago=0.0, lat=60.0, lon=25.0)]
        anomaly = {"rule_id": "sts_proximity", "event_start": _ts(6.0).isoformat()}

        with patch(
            "rules.sts_proximity._check_sts_zone_db",
            new_callable=AsyncMock,
            return_value="Kalamata STS",  # Still in zone
        ):
            result = await rule.check_event_ended(123456789, None, positions, anomaly)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_positions_does_not_end(self, rule):
        """No positions → cannot determine, returns False."""
        anomaly = {"rule_id": "sts_proximity", "event_start": _ts(6.0).isoformat()}
        result = await rule.check_event_ended(123456789, None, [], anomaly)
        assert result is False


# ===================================================================
# AIS Gap event boundary
# ===================================================================


class TestAisGapEventEnd:
    """Tests for AisGapRule.check_event_ended."""

    @pytest.fixture
    def rule(self):
        from rules.ais_gap import AisGapRule
        return AisGapRule()

    @pytest.mark.asyncio
    async def test_signal_resumes_ends_event(self, rule):
        """New position received after gap started → event ended."""
        event_start = _ts(6.0)
        positions = [_pos(hours_ago=0.5)]  # Position after gap started
        anomaly = {"rule_id": "ais_gap", "event_start": event_start.isoformat()}

        result = await rule.check_event_ended(123456789, None, positions, anomaly)
        assert result is True

    @pytest.mark.asyncio
    async def test_signal_resumes_with_created_at(self, rule):
        """Uses created_at if event_start is missing."""
        created_at = _ts(6.0)
        positions = [_pos(hours_ago=0.5)]
        anomaly = {"rule_id": "ais_gap", "created_at": created_at.isoformat()}

        result = await rule.check_event_ended(123456789, None, positions, anomaly)
        assert result is True

    @pytest.mark.asyncio
    async def test_no_new_positions_does_not_end(self, rule):
        """No positions after gap → event NOT ended."""
        event_start = _ts(1.0)
        positions = [_pos(hours_ago=2.0)]  # Position before gap started
        anomaly = {"rule_id": "ais_gap", "event_start": event_start.isoformat()}

        result = await rule.check_event_ended(123456789, None, positions, anomaly)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_positions_at_all(self, rule):
        """No positions → event NOT ended."""
        anomaly = {"rule_id": "ais_gap", "event_start": _ts(6.0).isoformat()}
        result = await rule.check_event_ended(123456789, None, [], anomaly)
        assert result is False

    @pytest.mark.asyncio
    async def test_event_start_as_datetime(self, rule):
        """event_start can be a datetime object, not just a string."""
        event_start = _ts(6.0)
        positions = [_pos(hours_ago=0.5)]
        anomaly = {"rule_id": "ais_gap", "event_start": event_start}

        result = await rule.check_event_ended(123456789, None, positions, anomaly)
        assert result is True


# ===================================================================
# Draft Change event boundary
# ===================================================================


class TestDraftChangeEventEnd:
    """Tests for DraftChangeRule.check_event_ended."""

    @pytest.fixture
    def rule(self):
        from rules.draft_change import DraftChangeRule
        return DraftChangeRule()

    @pytest.mark.asyncio
    async def test_draught_returns_to_normal_ends_event(self, rule):
        """Draught returns within 0.5m of earliest → event ended."""
        positions = [_pos(hours_ago=0.0, draught=10.3)]
        anomaly = {
            "rule_id": "draft_change",
            "event_start": _ts(6.0).isoformat(),
            "details": {"earliest_draught": 10.0, "latest_draught": 12.5},
        }
        result = await rule.check_event_ended(123456789, None, positions, anomaly)
        assert result is True

    @pytest.mark.asyncio
    async def test_draught_still_elevated_does_not_end(self, rule):
        """Draught still far from earliest → event NOT ended."""
        positions = [_pos(hours_ago=0.0, draught=12.5)]
        anomaly = {
            "rule_id": "draft_change",
            "event_start": _ts(6.0).isoformat(),
            "details": {"earliest_draught": 10.0, "latest_draught": 12.5},
        }
        result = await rule.check_event_ended(123456789, None, positions, anomaly)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_draught_data_does_not_end(self, rule):
        """No draught in positions → event NOT ended."""
        positions = [_pos(hours_ago=0.0)]  # No draught field
        anomaly = {
            "rule_id": "draft_change",
            "event_start": _ts(6.0).isoformat(),
            "details": {"earliest_draught": 10.0},
        }
        result = await rule.check_event_ended(123456789, None, positions, anomaly)
        assert result is False

    @pytest.mark.asyncio
    async def test_details_as_json_string(self, rule):
        """Details can be a JSON string."""
        import json
        positions = [_pos(hours_ago=0.0, draught=10.2)]
        anomaly = {
            "rule_id": "draft_change",
            "event_start": _ts(6.0).isoformat(),
            "details": json.dumps({"earliest_draught": 10.0}),
        }
        result = await rule.check_event_ended(123456789, None, positions, anomaly)
        assert result is True

    @pytest.mark.asyncio
    async def test_missing_earliest_draught_does_not_end(self, rule):
        """Missing earliest_draught in details → returns False."""
        positions = [_pos(hours_ago=0.0, draught=10.0)]
        anomaly = {
            "rule_id": "draft_change",
            "event_start": _ts(6.0).isoformat(),
            "details": {},
        }
        result = await rule.check_event_ended(123456789, None, positions, anomaly)
        assert result is False


# ===================================================================
# Destination Spoof event boundary
# ===================================================================


class TestDestinationSpoofEventEnd:
    """Tests for DestinationSpoofRule.check_event_ended."""

    @pytest.fixture
    def rule(self):
        from rules.destination_spoof import DestinationSpoofRule
        return DestinationSpoofRule()

    @pytest.mark.asyncio
    async def test_destination_changes_to_real_port_ends_event(self, rule):
        """Destination changes from placeholder to real port → event ended."""
        profile = {"destination": "ROTTERDAM"}
        anomaly = {
            "rule_id": "destination_spoof",
            "event_start": _ts(6.0).isoformat(),
            "details": {"destination": "FOR ORDERS", "reason": "placeholder_destination"},
        }
        result = await rule.check_event_ended(123456789, profile, [], anomaly)
        assert result is True

    @pytest.mark.asyncio
    async def test_destination_still_placeholder_does_not_end(self, rule):
        """Destination still a placeholder → event NOT ended."""
        profile = {"destination": "TBN"}
        anomaly = {
            "rule_id": "destination_spoof",
            "event_start": _ts(6.0).isoformat(),
            "details": {"destination": "FOR ORDERS"},
        }
        result = await rule.check_event_ended(123456789, profile, [], anomaly)
        assert result is False

    @pytest.mark.asyncio
    async def test_destination_still_sea_area_does_not_end(self, rule):
        """Destination still a sea area → event NOT ended."""
        profile = {"destination": "CARIBBEAN SEA"}
        anomaly = {
            "rule_id": "destination_spoof",
            "event_start": _ts(6.0).isoformat(),
            "details": {"destination": "MEDITERRANEAN"},
        }
        result = await rule.check_event_ended(123456789, profile, [], anomaly)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_profile_does_not_end(self, rule):
        """No profile → event NOT ended."""
        anomaly = {
            "rule_id": "destination_spoof",
            "event_start": _ts(6.0).isoformat(),
        }
        result = await rule.check_event_ended(123456789, None, [], anomaly)
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_destination_does_not_end(self, rule):
        """Empty destination → event NOT ended."""
        profile = {"destination": ""}
        anomaly = {
            "rule_id": "destination_spoof",
            "event_start": _ts(6.0).isoformat(),
        }
        result = await rule.check_event_ended(123456789, profile, [], anomaly)
        assert result is False

    @pytest.mark.asyncio
    async def test_destination_changes_to_specific_port(self, rule):
        """Destination changes from sea area to specific port → event ended."""
        profile = {"destination": "SINGAPORE"}
        anomaly = {
            "rule_id": "destination_spoof",
            "event_start": _ts(6.0).isoformat(),
            "details": {"destination": "ATLANTIC", "reason": "sea_area_destination"},
        }
        result = await rule.check_event_ended(123456789, profile, [], anomaly)
        assert result is True
