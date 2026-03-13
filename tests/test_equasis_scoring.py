"""Tests for Equasis-enhanced scoring rules.

Verifies that insurance_class_risk and flag_hopping rules correctly
incorporate Equasis PSC inspection data, classification status, and
flag history into their evaluations.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services.scoring.rules.insurance_class_risk import InsuranceClassRiskRule
from services.scoring.rules.flag_hopping import FlagHoppingRule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile(**overrides) -> dict:
    """Build a minimal vessel profile dict."""
    base = {
        "mmsi": 123456789,
        "ship_type": 70,  # cargo, not tanker
        "class_society": "DNV",
        "flag_country": "NO",
        "insurer": "Gard",
        "pi_tier": "IG",
        "pi_details": {"is_ig_member": True, "provider": "Gard"},
    }
    base.update(overrides)
    return base


def _date_str(days_ago: int) -> str:
    """Return a dd/mm/yyyy date string for N days ago."""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return f"{dt.day:02d}/{dt.month:02d}/{dt.year}"


# ===================================================================
# InsuranceClassRiskRule — PSC Inspections
# ===================================================================


class TestInsuranceClassRiskPSC:
    """PSC inspection findings from equasis_data."""

    @pytest.fixture
    def rule(self):
        return InsuranceClassRiskRule()

    @pytest.mark.asyncio
    async def test_psc_detention_recent_triggers_finding(self, rule):
        profile = _make_profile(
            equasis_data={
                "psc_inspections": [
                    {
                        "date": _date_str(100),
                        "detention": True,
                        "deficiencies": 3,
                    }
                ],
            }
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        detention_findings = [
            f for f in result.details["findings"] if f["check"] == "psc_detention"
        ]
        assert len(detention_findings) == 1
        assert detention_findings[0]["severity"] == "high"
        assert detention_findings[0]["points"] == 15
        assert detention_findings[0]["detention_count"] == 1

    @pytest.mark.asyncio
    async def test_psc_detention_string_y_triggers(self, rule):
        """Detention value 'Y' (string) should also trigger."""
        profile = _make_profile(
            equasis_data={
                "psc_inspections": [
                    {"date": _date_str(30), "detention": "Y", "deficiencies": 0}
                ],
            }
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        det = [f for f in result.details["findings"] if f["check"] == "psc_detention"]
        assert len(det) == 1

    @pytest.mark.asyncio
    async def test_psc_detention_older_than_3_years_ignored(self, rule):
        """Detentions older than 3 years should NOT trigger."""
        profile = _make_profile(
            equasis_data={
                "psc_inspections": [
                    {
                        "date": _date_str(4 * 365),  # 4 years ago
                        "detention": True,
                        "deficiencies": 2,
                    }
                ],
            }
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        # Should not fire (DNV + IG P&I = no base findings, old PSC = no equasis findings)
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_psc_two_detentions_capped(self, rule):
        """Multiple detentions: points capped at 2 * 15 = 30."""
        profile = _make_profile(
            equasis_data={
                "psc_inspections": [
                    {"date": _date_str(30), "detention": True, "deficiencies": 0},
                    {"date": _date_str(60), "detention": True, "deficiencies": 0},
                    {"date": _date_str(90), "detention": True, "deficiencies": 0},
                ],
            }
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        det = [f for f in result.details["findings"] if f["check"] == "psc_detention"]
        assert len(det) == 1
        assert det[0]["points"] == 30  # capped at 2 * 15
        assert det[0]["detention_count"] == 3  # actual count preserved

    @pytest.mark.asyncio
    async def test_psc_deficiencies_moderate_threshold(self, rule):
        """>10 deficiencies triggers moderate finding."""
        profile = _make_profile(
            equasis_data={
                "psc_inspections": [
                    {"date": _date_str(30), "detention": False, "deficiencies": 6},
                    {"date": _date_str(60), "detention": False, "deficiencies": 6},
                ],
            }
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        def_f = [
            f
            for f in result.details["findings"]
            if f["check"] == "psc_moderate_deficiencies"
        ]
        assert len(def_f) == 1
        assert def_f[0]["severity"] == "moderate"
        assert def_f[0]["points"] == 8
        assert def_f[0]["deficiency_count"] == 12

    @pytest.mark.asyncio
    async def test_psc_deficiencies_high_threshold(self, rule):
        """>25 deficiencies triggers high finding."""
        profile = _make_profile(
            equasis_data={
                "psc_inspections": [
                    {"date": _date_str(30), "detention": False, "deficiencies": 15},
                    {"date": _date_str(60), "detention": False, "deficiencies": 15},
                ],
            }
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        def_f = [
            f
            for f in result.details["findings"]
            if f["check"] == "psc_high_deficiencies"
        ]
        assert len(def_f) == 1
        assert def_f[0]["severity"] == "high"
        assert def_f[0]["points"] == 15
        assert def_f[0]["deficiency_count"] == 30

    @pytest.mark.asyncio
    async def test_psc_deficiencies_at_threshold_no_trigger(self, rule):
        """Exactly 10 deficiencies should NOT trigger (need >10)."""
        profile = _make_profile(
            equasis_data={
                "psc_inspections": [
                    {"date": _date_str(30), "detention": False, "deficiencies": 10},
                ],
            }
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        # No PSC finding, no base finding => does not fire
        assert result.fired is False


# ===================================================================
# InsuranceClassRiskRule — Classification Status
# ===================================================================


class TestInsuranceClassRiskClassification:
    """Classification status findings from equasis_data."""

    @pytest.fixture
    def rule(self):
        return InsuranceClassRiskRule()

    @pytest.mark.asyncio
    async def test_classification_withdrawn_by_society(self, rule):
        profile = _make_profile(
            equasis_data={
                "classification_status": [
                    {
                        "society": "Lloyd's Register",
                        "status": "Withdrawn",
                        "reason": "Withdrawn by society - owner request",
                    }
                ],
            }
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        cw = [
            f
            for f in result.details["findings"]
            if f["check"] == "classification_withdrawn_by_society"
        ]
        assert len(cw) == 1
        assert cw[0]["severity"] == "critical"
        assert cw[0]["points"] == 25

    @pytest.mark.asyncio
    async def test_classification_withdrawn_not_by_society_no_trigger(self, rule):
        """Withdrawn but NOT 'by society' should not trigger this check."""
        profile = _make_profile(
            equasis_data={
                "classification_status": [
                    {
                        "society": "DNV",
                        "status": "Withdrawn",
                        "reason": "Owner transferred to another society",
                    }
                ],
            }
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        # No classification_withdrawn_by_society finding
        if result.fired:
            cw = [
                f
                for f in result.details["findings"]
                if f["check"] == "classification_withdrawn_by_society"
            ]
            assert len(cw) == 0

    @pytest.mark.asyncio
    async def test_russian_register_iacs_withdrawn_combo(self, rule):
        profile = _make_profile(
            equasis_data={
                "classification_status": [
                    {
                        "society": "Russian Maritime Register",
                        "status": "Delivered",
                        "reason": "",
                    },
                    {
                        "society": "IACS Member Society",
                        "status": "Withdrawn",
                        "reason": "Transfer",
                    },
                ],
            }
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        rr = [
            f
            for f in result.details["findings"]
            if f["check"] == "russian_register_iacs_withdrawn"
        ]
        assert len(rr) == 1
        assert rr[0]["severity"] == "high"
        assert rr[0]["points"] == 20

    @pytest.mark.asyncio
    async def test_russian_register_iacs_no_double_count_with_withdrawn_by_society(
        self, rule
    ):
        """If 'withdrawn by society' already found, don't also add russian+iacs combo."""
        profile = _make_profile(
            equasis_data={
                "classification_status": [
                    {
                        "society": "Russian Maritime Register",
                        "status": "Delivered",
                        "reason": "",
                    },
                    {
                        "society": "IACS Member Society",
                        "status": "Withdrawn",
                        "reason": "Withdrawn by society - compliance",
                    },
                ],
            }
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        # Should have withdrawn_by_society but NOT russian_register_iacs_withdrawn
        cw = [
            f
            for f in result.details["findings"]
            if f["check"] == "classification_withdrawn_by_society"
        ]
        rr = [
            f
            for f in result.details["findings"]
            if f["check"] == "russian_register_iacs_withdrawn"
        ]
        assert len(cw) == 1
        assert len(rr) == 0


# ===================================================================
# InsuranceClassRiskRule — Graceful handling
# ===================================================================


class TestInsuranceClassRiskGraceful:
    """Existing behavior unchanged when no equasis_data."""

    @pytest.fixture
    def rule(self):
        return InsuranceClassRiskRule()

    @pytest.mark.asyncio
    async def test_no_equasis_data_no_change(self, rule):
        """Profile without equasis_data should behave as before."""
        profile = _make_profile()
        result = await rule.evaluate(123456789, profile, [], [], [])
        # DNV + IG P&I = clean vessel, should not fire
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_empty_equasis_data_no_crash(self, rule):
        """Empty equasis_data dict should not crash."""
        profile = _make_profile(equasis_data={})
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_equasis_data_with_none_psc(self, rule):
        """equasis_data with None psc_inspections should not crash."""
        profile = _make_profile(equasis_data={"psc_inspections": None})
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is False


# ===================================================================
# FlagHoppingRule — Equasis flag_history
# ===================================================================


class TestFlagHoppingEquasis:
    """Flag hopping rule using equasis flag_history."""

    @pytest.fixture
    def rule(self):
        return FlagHoppingRule()

    @pytest.mark.asyncio
    async def test_equasis_flags_within_window(self, rule):
        """Recent equasis flag changes should be counted."""
        profile = _make_profile(
            flag_country="PA",
            equasis_data={
                "flag_history": [
                    {"flag": "Panama", "date_of_effect": _date_str(30)},
                    {"flag": "Liberia", "date_of_effect": _date_str(90)},
                    {"flag": "Tanzania", "date_of_effect": _date_str(180)},
                ],
            },
        )
        # MMSI 123456789 -> MID 123 (not a real flag, but _flag_from_mmsi handles it)
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        # At least 3 flags from equasis + possibly flag_country
        assert result.details["flag_count"] >= 3

    @pytest.mark.asyncio
    async def test_equasis_old_flags_excluded(self, rule):
        """Flags older than 12 months should be excluded from equasis data."""
        profile = _make_profile(
            flag_country="PA",
            equasis_data={
                "flag_history": [
                    {"flag": "Liberia", "date_of_effect": _date_str(400)},
                    {"flag": "Tanzania", "date_of_effect": _date_str(500)},
                ],
            },
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        # Old flags excluded, so only current flag + flag_country at most
        if result.fired:
            assert result.details["flag_count"] <= 2

    @pytest.mark.asyncio
    async def test_equasis_many_flags_high_severity(self, rule):
        """14 flags in equasis history within window triggers high severity."""
        flags_data = []
        country_names = [
            "Panama", "Liberia", "Tanzania", "Cameroon", "Togo",
            "Comoros", "Palau", "Sierra Leone", "Bolivia", "Gabon",
            "Mongolia", "Honduras", "Belize", "Kiribati",
        ]
        for i, name in enumerate(country_names):
            flags_data.append({
                "flag": name,
                "date_of_effect": _date_str(i * 20 + 5),
            })

        profile = _make_profile(
            flag_country="PA",
            equasis_data={"flag_history": flags_data},
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.details["flag_count"] >= 3

    @pytest.mark.asyncio
    async def test_equasis_flag_history_no_date_included(self, rule):
        """Flag entries without date_of_effect should still be included."""
        profile = _make_profile(
            flag_country="PA",
            equasis_data={
                "flag_history": [
                    {"flag": "Liberia"},
                    {"flag": "Tanzania"},
                    {"flag": "Cameroon"},
                ],
            },
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.details["flag_count"] >= 3

    @pytest.mark.asyncio
    async def test_no_equasis_data_existing_behavior(self, rule):
        """Without equasis_data, existing flag_history behavior is unchanged."""
        profile = _make_profile(
            flag_country="PA",
            flag_history=[
                {"flag": "LR", "first_seen": datetime.now(timezone.utc).isoformat()},
                {"flag": "TZ", "first_seen": datetime.now(timezone.utc).isoformat()},
            ],
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.details["flag_count"] >= 2
