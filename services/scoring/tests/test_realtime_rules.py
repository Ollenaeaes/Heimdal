"""Tests for all 9 real-time scoring rules.

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

from shared.models.anomaly import RuleResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 12, 12, 0, 0, tzinfo=timezone.utc)


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
# Story 8: AIS Gap Detection
# ===================================================================


class TestAisGap:
    """Tests for rules/ais_gap.py."""

    @pytest.fixture
    def rule(self):
        from rules.ais_gap import AisGapRule
        return AisGapRule()

    @pytest.mark.asyncio
    async def test_49h_gap_fires_high(self, rule):
        profile = {"last_position_time": _ts(49)}
        with patch("rules.ais_gap._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0

    @pytest.mark.asyncio
    async def test_13h_gap_fires_moderate(self, rule):
        profile = {"last_position_time": _ts(13)}
        with patch("rules.ais_gap._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "moderate"
        assert result.points == 15.0

    @pytest.mark.asyncio
    async def test_3h_gap_fires_low(self, rule):
        profile = {"last_position_time": _ts(3)}
        with patch("rules.ais_gap._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "low"
        assert result.points == 5.0

    @pytest.mark.asyncio
    async def test_1h_gap_does_not_fire(self, rule):
        profile = {"last_position_time": _ts(1)}
        with patch("rules.ais_gap._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_cooldown_prevents_refiring(self, rule):
        """If ais_gap fired 12 h ago, cooldown blocks a new firing."""
        profile = {"last_position_time": _ts(49)}
        existing = [
            {"rule_id": "ais_gap", "created_at": _ts(12)},
        ]
        with patch("rules.ais_gap._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], existing, [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_no_profile_no_positions_returns_none(self, rule):
        result = await rule.evaluate(123456789, None, [], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_uses_recent_positions_when_no_profile_time(self, rule):
        """Falls back to recent_positions for last-seen time."""
        profile = {"last_position_time": None}
        positions = [_pos(hours_ago=50)]
        with patch("rules.ais_gap._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, positions, [], [])
        assert result.fired is True
        assert result.severity == "high"


# ===================================================================
# Story 9: STS Zone Proximity
# ===================================================================


class TestStsProximity:
    """Tests for rules/sts_proximity.py."""

    @pytest.fixture
    def rule(self):
        from rules.sts_proximity import StsProximityRule
        return StsProximityRule()

    @pytest.mark.asyncio
    async def test_inside_sts_zone_slow_over_6h_fires(self, rule):
        """Vessel near STS zone, slow speed, >6h duration -> moderate."""
        positions = [
            _pos(hours_ago=8, sog=1.0, lat=36.5, lon=31.0),
            _pos(hours_ago=6, sog=2.0, lat=36.5, lon=31.0),
            _pos(hours_ago=4, sog=1.5, lat=36.5, lon=31.0),
            _pos(hours_ago=1, sog=2.5, lat=36.5, lon=31.0),
        ]

        async def mock_check(positions_arg):
            return "Kalamata STS Zone"

        with patch("rules.sts_proximity._check_sts_zone_db", side_effect=mock_check):
            result = await rule.evaluate(123456789, {}, positions, [], [])

        assert result.fired is True
        assert result.severity == "moderate"
        assert result.points == 15.0
        assert result.details["zone_name"] == "Kalamata STS Zone"

    @pytest.mark.asyncio
    async def test_inside_sts_zone_fast_does_not_fire(self, rule):
        """Vessel near STS zone but going fast -> does not fire."""
        positions = [
            _pos(hours_ago=8, sog=12.0),
            _pos(hours_ago=4, sog=11.0),
            _pos(hours_ago=1, sog=13.0),
        ]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_inside_sts_zone_less_than_6h_does_not_fire(self, rule):
        """Vessel near STS zone, slow, but <6h duration -> does not fire."""
        positions = [
            _pos(hours_ago=3, sog=1.0),
            _pos(hours_ago=1, sog=2.0),
        ]

        async def mock_check(positions_arg):
            return "Kalamata STS Zone"

        with patch("rules.sts_proximity._check_sts_zone_db", side_effect=mock_check):
            result = await rule.evaluate(123456789, {}, positions, [], [])

        assert result.fired is False

    @pytest.mark.asyncio
    async def test_no_positions_returns_none(self, rule):
        result = await rule.evaluate(123456789, {}, [], [], [])
        assert result is None


# ===================================================================
# Story 10: Destination Spoofing
# ===================================================================


class TestDestinationSpoof:
    """Tests for rules/destination_spoof.py."""

    @pytest.fixture
    def rule(self):
        from rules.destination_spoof import DestinationSpoofRule
        return DestinationSpoofRule()

    @pytest.mark.asyncio
    async def test_for_orders_fires_high(self, rule):
        profile = {"destination": "FOR ORDERS"}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0

    @pytest.mark.asyncio
    async def test_tbn_fires_high(self, rule):
        profile = {"destination": "TBN"}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0

    @pytest.mark.asyncio
    async def test_mediterranean_fires_high(self, rule):
        profile = {"destination": "MEDITERRANEAN"}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0

    @pytest.mark.asyncio
    async def test_caribbean_sea_fires_high(self, rule):
        profile = {"destination": "Caribbean Sea"}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0

    @pytest.mark.asyncio
    async def test_normal_port_does_not_fire(self, rule):
        profile = {"destination": "ROTTERDAM"}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_no_profile_returns_none(self, rule):
        result = await rule.evaluate(123456789, None, [], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_destination_returns_none(self, rule):
        profile = {"destination": ""}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_frequent_changes_fires_moderate(self, rule):
        """4 destination changes in 7 days fires moderate."""
        profile = {"destination": "SINGAPORE"}
        existing = [
            {
                "rule_id": "destination_spoof",
                "created_at": _ts(24),
                "details": {"destination": "FOR ORDERS"},
            },
            {
                "rule_id": "destination_spoof",
                "created_at": _ts(48),
                "details": {"destination": "MEDITERRANEAN"},
            },
            {
                "rule_id": "destination_spoof",
                "created_at": _ts(72),
                "details": {"destination": "TBN"},
            },
            {
                "rule_id": "destination_spoof",
                "created_at": _ts(96),
                "details": {"destination": "ATLANTIC"},
            },
        ]
        with patch("rules.destination_spoof._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], existing, [])
        assert result.fired is True
        assert result.severity == "moderate"
        assert result.points == 15.0


# ===================================================================
# Story 11: Draft Change Detection
# ===================================================================


class TestDraftChange:
    """Tests for rules/draft_change.py."""

    @pytest.fixture
    def rule(self):
        from rules.draft_change import DraftChangeRule
        return DraftChangeRule()

    @pytest.mark.asyncio
    async def test_3m_increase_drifting_at_sea_fires_high(self, rule):
        """3m draught increase while drifting, not near terminal."""
        positions = [
            _pos(hours_ago=6, sog=0.5, nav_status=5, draught=8.0),
            _pos(hours_ago=3, sog=0.3, nav_status=5, draught=9.5),
            _pos(hours_ago=1, sog=0.2, nav_status=5, draught=11.0),
        ]

        async def mock_terminal(lat, lon):
            return False

        with patch("rules.draft_change._check_near_terminal_db", side_effect=mock_terminal):
            result = await rule.evaluate(123456789, {}, positions, [], [])

        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0
        assert result.details["draught_increase_m"] == 3.0

    @pytest.mark.asyncio
    async def test_3m_increase_at_port_does_not_fire(self, rule):
        """3m draught increase near a terminal -> does not fire."""
        positions = [
            _pos(hours_ago=6, sog=0.5, nav_status=5, draught=8.0),
            _pos(hours_ago=1, sog=0.2, nav_status=5, draught=11.0),
        ]

        async def mock_terminal(lat, lon):
            return True

        with patch("rules.draft_change._check_near_terminal_db", side_effect=mock_terminal):
            result = await rule.evaluate(123456789, {}, positions, [], [])

        assert result.fired is False

    @pytest.mark.asyncio
    async def test_1m_increase_does_not_fire(self, rule):
        """<2m increase -> does not fire."""
        positions = [
            _pos(hours_ago=6, sog=0.5, nav_status=5, draught=8.0),
            _pos(hours_ago=1, sog=0.2, nav_status=5, draught=9.0),
        ]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_insufficient_positions_returns_none(self, rule):
        positions = [_pos(hours_ago=1, draught=10.0)]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_no_draught_data_returns_none(self, rule):
        positions = [_pos(hours_ago=6), _pos(hours_ago=1)]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result is None


# ===================================================================
# Story 12: Flag Hopping
# ===================================================================


class TestFlagHopping:
    """Tests for rules/flag_hopping.py."""

    @pytest.fixture
    def rule(self):
        from rules.flag_hopping import FlagHoppingRule
        return FlagHoppingRule()

    @pytest.mark.asyncio
    async def test_3_flags_in_12_months_fires_high(self, rule):
        """3 distinct flags -> high severity."""
        # MMSI 211xxx = Germany (DE), profile flag GB, history has PA
        profile = {
            "flag_country": "GB",
            "flag_history": [
                {"flag": "PA", "first_seen": _ts(24 * 100).isoformat()},
            ],
        }
        with patch("rules.flag_hopping._utcnow", return_value=_NOW):
            result = await rule.evaluate(211000000, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0
        assert result.details["flag_count"] == 3

    @pytest.mark.asyncio
    async def test_2_flags_fires_moderate(self, rule):
        """2 distinct flags -> moderate severity."""
        # MMSI 211xxx = DE, profile flag also DE but history has GB
        profile = {
            "flag_country": "DE",
            "flag_history": [
                {"flag": "GB", "first_seen": _ts(24 * 100).isoformat()},
            ],
        }
        with patch("rules.flag_hopping._utcnow", return_value=_NOW):
            result = await rule.evaluate(211000000, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "moderate"
        assert result.points == 15.0

    @pytest.mark.asyncio
    async def test_1_flag_does_not_fire(self, rule):
        """Single flag -> does not fire."""
        profile = {"flag_country": "DE"}
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_mid_extraction(self, rule):
        """MID 351 = Panama (PA)."""
        flag = rule._flag_from_mmsi(351000000)
        assert flag == "PA"

    @pytest.mark.asyncio
    async def test_no_profile_returns_none(self, rule):
        result = await rule.evaluate(123456789, None, [], [], [])
        assert result is None


# ===================================================================
# Story 13a: Sanctions Match
# ===================================================================


class TestSanctionsMatch:
    """Tests for rules/sanctions_match.py."""

    @pytest.fixture
    def rule(self):
        from rules.sanctions_match import SanctionsMatchRule
        return SanctionsMatchRule()

    @pytest.mark.asyncio
    async def test_direct_match_fires_critical(self, rule):
        profile = {
            "sanctions_status": {
                "matches": [
                    {
                        "entity_id": "SDN-12345",
                        "program": "OFAC",
                        "confidence": 0.95,
                        "matched_field": "imo",
                    }
                ]
            }
        }
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "critical"
        assert result.points == 100.0
        assert result.details["match_type"] == "direct"

    @pytest.mark.asyncio
    async def test_fuzzy_match_fires_high(self, rule):
        profile = {
            "sanctions_status": {
                "matches": [
                    {
                        "entity_id": "EU-9876",
                        "program": "EU",
                        "confidence": 0.55,
                        "matched_field": "ship_name",
                    }
                ]
            }
        }
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0
        assert result.details["match_type"] == "fuzzy"

    @pytest.mark.asyncio
    async def test_no_sanctions_does_not_fire(self, rule):
        profile = {"sanctions_status": None}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_empty_matches_does_not_fire(self, rule):
        profile = {"sanctions_status": {"matches": []}}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_no_profile_returns_none(self, rule):
        result = await rule.evaluate(123456789, None, [], [], [])
        assert result is None


# ===================================================================
# Story 13b: Vessel Age
# ===================================================================


class TestVesselAge:
    """Tests for rules/vessel_age.py."""

    @pytest.fixture
    def rule(self):
        from rules.vessel_age import VesselAgeRule
        return VesselAgeRule()

    @pytest.mark.asyncio
    async def test_25yo_tanker_fires_high(self, rule):
        """25-year-old tanker (2026 - 2001 = 25) -> high."""
        profile = {"ship_type": 80, "build_year": 2001}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0

    @pytest.mark.asyncio
    async def test_17yo_tanker_fires_low(self, rule):
        """17-year-old tanker (2026 - 2009 = 17) -> low."""
        profile = {"ship_type": 85, "build_year": 2009}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "low"
        assert result.points == 5.0

    @pytest.mark.asyncio
    async def test_non_tanker_does_not_fire(self, rule):
        """Bulk carrier (ship_type 70) -> does not fire."""
        profile = {"ship_type": 70, "build_year": 2001}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_young_tanker_does_not_fire(self, rule):
        """10-year-old tanker -> does not fire."""
        profile = {"ship_type": 80, "build_year": 2016}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_no_build_year_returns_none(self, rule):
        profile = {"ship_type": 80, "build_year": None}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_no_profile_returns_none(self, rule):
        result = await rule.evaluate(123456789, None, [], [], [])
        assert result is None


# ===================================================================
# Story 13c: Speed Anomaly
# ===================================================================


class TestSpeedAnomaly:
    """Tests for rules/speed_anomaly.py."""

    @pytest.fixture
    def rule(self):
        from rules.speed_anomaly import SpeedAnomalyRule
        return SpeedAnomalyRule()

    @pytest.mark.asyncio
    async def test_sustained_slow_steaming_fires(self, rule):
        """<5 knots average for >2 hours -> moderate."""
        positions = [
            _pos(hours_ago=3, sog=3.0),
            _pos(hours_ago=2, sog=4.0),
            _pos(hours_ago=0.5, sog=2.5),
        ]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result.fired is True
        assert result.severity == "moderate"
        assert result.points == 15.0
        assert result.details["reason"] == "sustained_slow_steaming"

    @pytest.mark.asyncio
    async def test_abrupt_speed_change_fires(self, rule):
        """>10 knot delta between consecutive positions -> moderate."""
        positions = [
            _pos(hours_ago=2, sog=2.0),
            _pos(hours_ago=1, sog=15.0),  # delta = 13
        ]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result.fired is True
        assert result.severity == "moderate"
        assert result.points == 15.0
        assert result.details["reason"] == "abrupt_speed_change"

    @pytest.mark.asyncio
    async def test_normal_speed_does_not_fire(self, rule):
        positions = [
            _pos(hours_ago=3, sog=12.0),
            _pos(hours_ago=2, sog=11.5),
            _pos(hours_ago=1, sog=12.5),
        ]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_insufficient_positions_returns_none(self, rule):
        positions = [_pos(hours_ago=1, sog=3.0)]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result is None


# ===================================================================
# Story 13d: Identity Mismatch
# ===================================================================


class TestIdentityMismatch:
    """Tests for rules/identity_mismatch.py."""

    @pytest.fixture
    def rule(self):
        from rules.identity_mismatch import IdentityMismatchRule
        return IdentityMismatchRule()

    @pytest.mark.asyncio
    async def test_dimension_mismatch_fires_critical(self, rule):
        """>20% dimension diff -> critical."""
        profile = {
            "imo_length": 200.0,
            "length": 150.0,  # 25% diff — exceeds 20% threshold
            "imo_width": 30.0,
            "width": 30.0,
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "critical"
        assert result.points == 100.0

    @pytest.mark.asyncio
    async def test_flag_mismatch_fires_high(self, rule):
        """MMSI says DE but profile says PA -> high."""
        profile = {
            "flag_country": "PA",
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0
        assert result.details["reason"] == "flag_mismatch"
        assert result.details["mmsi_derived_flag"] == "DE"
        assert result.details["reported_flag"] == "PA"

    @pytest.mark.asyncio
    async def test_matching_dimensions_and_flag_does_not_fire(self, rule):
        profile = {
            "flag_country": "DE",
            "imo_length": 200.0,
            "length": 200.0,
            "imo_width": 30.0,
            "width": 30.0,
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_no_reference_dimensions_checks_flag_only(self, rule):
        """No imo_length/imo_width -> skip dimension check, check flag."""
        profile = {
            "length": 200.0,
            "width": 30.0,
            "flag_country": "DE",
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_no_profile_returns_none(self, rule):
        result = await rule.evaluate(123456789, None, [], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_dimension_mismatch_takes_priority_over_flag(self, rule):
        """Dimension mismatch (critical) fires before flag mismatch (high)."""
        profile = {
            "imo_length": 200.0,
            "length": 100.0,  # 50% diff
            "flag_country": "PA",  # also mismatched
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "critical"
        assert result.details["reason"] == "dimension_mismatch"


# ===================================================================
# Cross-rule: source field
# ===================================================================


class TestRealtimeRuleSource:
    """All realtime rules must set source='realtime' on fired results."""

    @pytest.mark.asyncio
    async def test_ais_gap_source(self):
        from rules.ais_gap import AisGapRule
        rule = AisGapRule()
        profile = {"last_position_time": _ts(49)}
        with patch("rules.ais_gap._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.source == "realtime"

    @pytest.mark.asyncio
    async def test_sanctions_source(self):
        from rules.sanctions_match import SanctionsMatchRule
        rule = SanctionsMatchRule()
        profile = {"sanctions_status": {"matches": [{"confidence": 0.95}]}}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.source == "realtime"

    @pytest.mark.asyncio
    async def test_vessel_age_source(self):
        from rules.vessel_age import VesselAgeRule
        rule = VesselAgeRule()
        profile = {"ship_type": 80, "build_year": 2001}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.source == "realtime"
