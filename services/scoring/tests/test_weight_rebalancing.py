"""Tests for Story 6 weight rebalancing: updated caps, progressive vessel age,
two-tier flag of convenience, and new rule/constant entries.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make imports work
_scoring_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scoring_dir))
sys.path.insert(0, str(_scoring_dir.parent.parent))

from shared.constants import (
    ALL_RULE_IDS,
    FRAUDULENT_REGISTRY_FLAGS,
    GFW_RULE_IDS,
    MAX_PER_RULE,
    REALTIME_RULE_IDS,
    SHADOW_FLEET_DESTINATIONS,
    SHADOW_FLEET_FLAGS,
)


# ---------------------------------------------------------------------------
# MAX_PER_RULE cap changes
# ---------------------------------------------------------------------------


class TestMaxPerRuleCaps:
    """Verify updated and new MAX_PER_RULE entries."""

    def test_speed_anomaly_cap_is_10(self):
        """speed_anomaly cap changed from 15 to 10."""
        assert MAX_PER_RULE["speed_anomaly"] == 10

    def test_ais_spoofing_cap(self):
        assert MAX_PER_RULE["ais_spoofing"] == 100

    def test_ownership_risk_cap(self):
        assert MAX_PER_RULE["ownership_risk"] == 60

    def test_insurance_class_risk_cap(self):
        assert MAX_PER_RULE["insurance_class_risk"] == 60

    def test_voyage_pattern_cap(self):
        assert MAX_PER_RULE["voyage_pattern"] == 80


# ---------------------------------------------------------------------------
# Rule ID sets
# ---------------------------------------------------------------------------


class TestRuleIdSets:
    """Verify new rules appear in the correct ID sets."""

    def test_all_rule_ids_includes_new_rules(self):
        for rule_id in ("ais_spoofing", "ownership_risk", "insurance_class_risk", "voyage_pattern"):
            assert rule_id in ALL_RULE_IDS, f"{rule_id} missing from ALL_RULE_IDS"

    def test_realtime_rule_ids_includes_new_realtime_rules(self):
        for rule_id in ("ais_spoofing", "ownership_risk", "insurance_class_risk"):
            assert rule_id in REALTIME_RULE_IDS, f"{rule_id} missing from REALTIME_RULE_IDS"

    def test_gfw_rule_ids_includes_voyage_pattern(self):
        assert "voyage_pattern" in GFW_RULE_IDS


# ---------------------------------------------------------------------------
# New constants
# ---------------------------------------------------------------------------


class TestNewConstants:
    """Verify FRAUDULENT_REGISTRY_FLAGS and SHADOW_FLEET_DESTINATIONS."""

    def test_fraudulent_registry_flags_contains_expected(self):
        expected = {"CM", "KM", "PW", "GA", "TZ", "GM", "MW", "SL"}
        assert FRAUDULENT_REGISTRY_FLAGS == expected

    def test_shadow_fleet_destinations_contains_indian_ports(self):
        for port in ("SIKKA", "JAMNAGAR", "PARADIP", "VADINAR", "MUMBAI", "CHENNAI"):
            assert port in SHADOW_FLEET_DESTINATIONS

    def test_shadow_fleet_destinations_contains_chinese_ports(self):
        for port in ("QINGDAO", "RIZHAO", "DONGYING", "ZHOUSHAN", "NINGBO", "DALIAN"):
            assert port in SHADOW_FLEET_DESTINATIONS

    def test_shadow_fleet_destinations_contains_turkish_ports(self):
        for port in ("ISKENDERUN", "MERSIN", "ALIAGA", "DORTYOL", "CEYHAN"):
            assert port in SHADOW_FLEET_DESTINATIONS


# ---------------------------------------------------------------------------
# Vessel age progressive scoring
# ---------------------------------------------------------------------------


class TestVesselAgeProgressive:
    """Verify three-tier progressive scoring for vessel_age rule."""

    @pytest.fixture
    def rule(self):
        from rules.vessel_age import VesselAgeRule
        return VesselAgeRule()

    @pytest.mark.asyncio
    async def test_18yo_tanker_fires_low_5pts(self, rule):
        """18-year-old tanker (2026 - 2008 = 18) -> low, 5 pts."""
        profile = {"ship_type": 80, "build_year": 2008}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "low"
        assert result.points == 5.0

    @pytest.mark.asyncio
    async def test_22yo_tanker_fires_moderate_15pts(self, rule):
        """22-year-old tanker (2026 - 2004 = 22) -> moderate, 15 pts."""
        profile = {"ship_type": 80, "build_year": 2004}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "moderate"
        assert result.points == 15.0

    @pytest.mark.asyncio
    async def test_27yo_tanker_fires_high_25pts(self, rule):
        """27-year-old tanker (2026 - 1999 = 27) -> high, 25 pts."""
        profile = {"ship_type": 80, "build_year": 1999}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 25.0

    @pytest.mark.asyncio
    async def test_boundary_15yo_fires_low(self, rule):
        """Exactly 15 years (2026 - 2011 = 15) -> low."""
        profile = {"ship_type": 80, "build_year": 2011}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "low"

    @pytest.mark.asyncio
    async def test_boundary_20yo_fires_moderate(self, rule):
        """Exactly 20 years (2026 - 2006 = 20) -> moderate."""
        profile = {"ship_type": 80, "build_year": 2006}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "moderate"

    @pytest.mark.asyncio
    async def test_boundary_25yo_fires_high(self, rule):
        """Exactly 25 years (2026 - 2001 = 25) -> high."""
        profile = {"ship_type": 80, "build_year": 2001}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"

    @pytest.mark.asyncio
    async def test_14yo_tanker_does_not_fire(self, rule):
        """14-year-old tanker -> does not fire."""
        profile = {"ship_type": 80, "build_year": 2012}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is False


# ---------------------------------------------------------------------------
# Flag of convenience two-tier scoring
# ---------------------------------------------------------------------------


class TestFlagOfConvenienceTwoTier:
    """Verify two-tier FoC scoring: fraudulent registries vs standard FoC."""

    @pytest.fixture
    def rule(self):
        from rules.flag_of_convenience import FlagOfConvenienceRule
        return FlagOfConvenienceRule()

    @pytest.mark.asyncio
    async def test_cameroon_fires_high_20pts(self, rule):
        """Cameroon (CM) is a fraudulent registry -> high, 20 pts."""
        profile = {"flag_country": "CM"}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 20.0

    @pytest.mark.asyncio
    async def test_comoros_fires_high_20pts(self, rule):
        """Comoros (KM) is a fraudulent registry -> high, 20 pts."""
        profile = {"flag_country": "KM"}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 20.0

    @pytest.mark.asyncio
    async def test_panama_fires_low_5pts(self, rule):
        """Panama (PA) is standard FoC -> low, 5 pts."""
        profile = {"flag_country": "PA"}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "low"
        assert result.points == 5.0

    @pytest.mark.asyncio
    async def test_liberia_fires_low_5pts(self, rule):
        """Liberia (LR) is standard FoC -> low, 5 pts."""
        profile = {"flag_country": "LR"}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "low"
        assert result.points == 5.0

    @pytest.mark.asyncio
    async def test_norway_does_not_fire(self, rule):
        """Norway (NO) is not FoC or fraudulent -> does not fire."""
        profile = {"flag_country": "NO"}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_gambia_fires_high_20pts(self, rule):
        """Gambia (GM) is in FRAUDULENT_REGISTRY_FLAGS -> high, 20 pts."""
        profile = {"flag_country": "GM"}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 20.0

    @pytest.mark.asyncio
    async def test_sierra_leone_fires_high_20pts(self, rule):
        """Sierra Leone (SL) is in FRAUDULENT_REGISTRY_FLAGS -> high, 20 pts."""
        profile = {"flag_country": "SL"}
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 20.0
