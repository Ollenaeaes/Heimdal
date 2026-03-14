"""Tests for services/scoring/rules/spoof_identity_mismatch.py."""

import pytest

from services.scoring.rules.spoof_identity_mismatch import SpoofIdentityMismatchRule


@pytest.fixture
def rule():
    return SpoofIdentityMismatchRule()


class TestSpoofIdentityMismatchRule:
    """Test the spoof_identity_mismatch rule."""

    def test_rule_id(self, rule):
        assert rule.rule_id == "spoof_identity_mismatch"

    def test_rule_category(self, rule):
        assert rule.rule_category == "realtime"

    @pytest.mark.asyncio
    async def test_no_profile_returns_none(self, rule):
        result = await rule.evaluate(211000000, None, [], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_no_gfw_data_returns_none(self, rule):
        """Without GFW data, rule should not fire."""
        profile = {"length": 200, "width": 30}
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_no_gfw_data_key_returns_none(self, rule):
        """Profile with empty gfw_data should not fire."""
        profile = {"length": 200, "width": 30, "gfw_data": None}
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_matching_data_does_not_fire(self, rule):
        """Consistent data across AIS and registry should not fire."""
        profile = {
            "length": 200,
            "width": 30,
            "flag_country": "DE",
            "gfw_data": {
                "length": 200,
                "beam": 30,
                "flag": "DE",
            },
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_zombie_vessel_fires_critical(self, rule):
        """IMO belonging to scrapped vessel → critical, 100 points."""
        profile = {
            "imo": 1234567,
            "gfw_data": {
                "vessel_status": "Scrapped",
            },
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result is not None
        assert result.fired is True
        assert result.severity == "critical"
        assert result.points == 100.0
        assert result.details["reason"] == "zombie_vessel"

    @pytest.mark.asyncio
    async def test_zombie_broken_up(self, rule):
        """'Broken Up' status should also trigger zombie detection."""
        profile = {
            "imo": 1234567,
            "gfw_data": {"vessel_status": "Broken Up"},
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result is not None
        assert result.fired is True
        assert result.details["reason"] == "zombie_vessel"

    @pytest.mark.asyncio
    async def test_zombie_total_loss(self, rule):
        profile = {
            "imo": 1234567,
            "gfw_data": {"status": "Total Loss"},
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result is not None
        assert result.fired is True
        assert result.details["reason"] == "zombie_vessel"

    @pytest.mark.asyncio
    async def test_dimension_mismatch_fires_high(self, rule):
        """Length or beam >20% different → high, 40 points."""
        profile = {
            "length": 250,  # AIS says 250m
            "width": 30,
            "gfw_data": {
                "length": 180,  # Registry says 180m → 38.9% diff
                "beam": 30,
            },
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result is not None
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0
        assert result.details["reason"] == "dimension_mismatch"

    @pytest.mark.asyncio
    async def test_beam_mismatch(self, rule):
        """Beam mismatch should also trigger."""
        profile = {
            "length": 200,
            "width": 50,  # AIS says 50m beam
            "gfw_data": {
                "length": 200,
                "beam": 30,  # Registry says 30m → 66% diff
            },
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result is not None
        assert result.fired is True
        assert result.details["reason"] == "dimension_mismatch"

    @pytest.mark.asyncio
    async def test_small_dimension_difference_does_not_fire(self, rule):
        """<20% dimension difference should not fire."""
        profile = {
            "length": 205,  # 2.5% off from 200
            "width": 31,   # 3.3% off from 30
            "gfw_data": {
                "length": 200,
                "beam": 30,
            },
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_flag_mid_mismatch_fires_high(self, rule):
        """MMSI MID != registered flag → high, 40 points."""
        # MMSI 211xxx = Germany (DE), but GFW says flag = PA (Panama)
        profile = {
            "gfw_data": {
                "flag": "PA",
            },
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result is not None
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 40.0
        assert result.details["reason"] == "flag_mid_mismatch"
        assert result.details["mmsi_derived_flag"] == "DE"
        assert result.details["registered_flag"] == "PA"

    @pytest.mark.asyncio
    async def test_matching_flag_does_not_fire(self, rule):
        """MMSI MID matches registered flag → should not fire."""
        # MMSI 211xxx = Germany (DE), GFW says DE
        profile = {
            "gfw_data": {"flag": "DE"},
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_zombie_takes_precedence_over_dimension(self, rule):
        """Zombie vessel (critical) should win over dimension mismatch (high)."""
        profile = {
            "imo": 1234567,
            "length": 250,
            "gfw_data": {
                "vessel_status": "Scrapped",
                "length": 180,
            },
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result is not None
        assert result.fired is True
        assert result.severity == "critical"
        assert result.details["reason"] == "zombie_vessel"

    @pytest.mark.asyncio
    async def test_no_registered_flag_does_not_fire_flag_check(self, rule):
        """If no registered flag data, flag check should not fire."""
        profile = {
            "gfw_data": {"some_field": "value"},  # has data but no flag info
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result is not None
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_gfw_vessel_info_key_also_works(self, rule):
        """Profile with gfw_vessel_info instead of gfw_data should work."""
        profile = {
            "imo": 1234567,
            "gfw_vessel_info": {
                "vessel_status": "Scrapped",
            },
        }
        result = await rule.evaluate(211000000, profile, [], [], [])
        assert result is not None
        assert result.fired is True
