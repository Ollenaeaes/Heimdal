"""Tests for shared.constants module."""

import pytest

from shared.constants import (
    MID_TO_FLAG,
    MAX_PER_RULE,
    SEVERITY_POINTS,
    ALL_RULE_IDS,
    GFW_RULE_IDS,
    REALTIME_RULE_IDS,
    SHADOW_FLEET_FLAGS,
)


class TestMidToFlag:
    """MID_TO_FLAG lookup table tests."""

    def test_is_dict(self):
        assert isinstance(MID_TO_FLAG, dict)

    def test_has_at_least_200_entries(self):
        assert len(MID_TO_FLAG) >= 200

    def test_russia_273(self):
        assert MID_TO_FLAG[273] == "RU"

    def test_panama_351_354(self):
        for mid in (351, 352, 353, 354):
            assert MID_TO_FLAG[mid] == "PA"

    def test_panama_370_373(self):
        for mid in (370, 371, 372, 373):
            assert MID_TO_FLAG[mid] == "PA"

    def test_liberia_636_637(self):
        assert MID_TO_FLAG[636] == "LR"
        assert MID_TO_FLAG[637] == "LR"

    def test_marshall_islands_538(self):
        assert MID_TO_FLAG[538] == "MH"

    def test_iran_422(self):
        assert MID_TO_FLAG[422] == "IR"

    def test_hong_kong_477(self):
        assert MID_TO_FLAG[477] == "HK"

    def test_tuvalu_572(self):
        assert MID_TO_FLAG[572] == "TV"

    def test_cameroon_613(self):
        assert MID_TO_FLAG[613] == "CM"

    def test_united_states_338(self):
        assert MID_TO_FLAG[338] == "US"

    def test_germany_211(self):
        assert MID_TO_FLAG[211] == "DE"

    def test_united_kingdom_232_235(self):
        for mid in (232, 233, 234, 235):
            assert MID_TO_FLAG[mid] == "GB"

    def test_all_values_are_two_letter_codes(self):
        for mid, code in MID_TO_FLAG.items():
            assert isinstance(mid, int), f"Key {mid} is not int"
            assert isinstance(code, str) and len(code) == 2, (
                f"Value for MID {mid} is not a 2-letter code: {code}"
            )


class TestMaxPerRule:
    """MAX_PER_RULE scoring caps tests."""

    def test_is_dict(self):
        assert isinstance(MAX_PER_RULE, dict)

    def test_has_13_rules(self):
        assert len(MAX_PER_RULE) == 13

    def test_gfw_rules_present(self):
        expected_gfw = {
            "gfw_ais_disabling",
            "gfw_encounter",
            "gfw_loitering",
            "gfw_port_visit",
            "gfw_dark_sar",
        }
        assert expected_gfw.issubset(set(MAX_PER_RULE.keys()))

    def test_realtime_rules_present(self):
        expected_rt = {
            "ais_gap",
            "sts_proximity",
            "destination_spoof",
            "draft_change",
            "flag_hopping",
            "sanctions_match",
            "vessel_age",
            "speed_anomaly",
        }
        assert expected_rt.issubset(set(MAX_PER_RULE.keys()))

    def test_all_values_are_positive_ints(self):
        for rule_id, cap in MAX_PER_RULE.items():
            assert isinstance(cap, int) and cap > 0, (
                f"Rule {rule_id} has invalid cap: {cap}"
            )

    def test_all_rule_ids_frozenset(self):
        assert isinstance(ALL_RULE_IDS, frozenset)
        assert len(ALL_RULE_IDS) == 13


class TestSeverityPoints:
    """Severity point value tests."""

    def test_has_four_levels(self):
        assert set(SEVERITY_POINTS.keys()) == {
            "critical",
            "high",
            "moderate",
            "low",
        }

    def test_critical_is_highest(self):
        assert SEVERITY_POINTS["critical"] > SEVERITY_POINTS["high"]
        assert SEVERITY_POINTS["high"] > SEVERITY_POINTS["moderate"]
        assert SEVERITY_POINTS["moderate"] > SEVERITY_POINTS["low"]

    def test_expected_values(self):
        assert SEVERITY_POINTS["critical"] == 25
        assert SEVERITY_POINTS["high"] == 15
        assert SEVERITY_POINTS["moderate"] == 8
        assert SEVERITY_POINTS["low"] == 3


class TestRuleIdLists:
    """GFW and realtime rule ID list tests."""

    def test_gfw_has_5_rules(self):
        assert len(GFW_RULE_IDS) == 5

    def test_realtime_has_8_rules(self):
        assert len(REALTIME_RULE_IDS) == 8

    def test_combined_equals_13(self):
        combined = set(GFW_RULE_IDS) | set(REALTIME_RULE_IDS)
        assert len(combined) == 13
        assert combined == ALL_RULE_IDS


class TestShadowFleetFlags:
    """Shadow fleet flag set tests."""

    def test_is_frozenset(self):
        assert isinstance(SHADOW_FLEET_FLAGS, frozenset)

    def test_contains_key_flags(self):
        for flag in ("RU", "PA", "LR", "MH", "IR"):
            assert flag in SHADOW_FLEET_FLAGS
