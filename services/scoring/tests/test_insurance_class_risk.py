"""Tests for the Insurance and Classification Risk scoring rule."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Make imports work
_scoring_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scoring_dir))
sys.path.insert(0, str(_scoring_dir.parent.parent))

from shared.models.anomaly import RuleResult


@pytest.fixture
def rule():
    from rules.insurance_class_risk import InsuranceClassRiskRule
    return InsuranceClassRiskRule()


def _profile(
    ship_type: int = 80,
    class_society: str | None = "DNV",
    pi_tier: str | None = "IG",
    pi_details: dict | None = None,
    insurer: str | None = None,
    previous_class_society: str | None = None,
    class_change_date: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a vessel profile dict."""
    p: dict[str, Any] = {"ship_type": ship_type}
    if class_society is not None:
        p["class_society"] = class_society
    if pi_tier is not None:
        p["pi_tier"] = pi_tier
    if pi_details is not None:
        p["pi_details"] = pi_details
    if insurer is not None:
        p["insurer"] = insurer
    if previous_class_society is not None:
        p["previous_class_society"] = previous_class_society
    if class_change_date is not None:
        p["class_change_date"] = class_change_date
    p.update(extra)
    return p


# -------------------------------------------------------------------
# Test: Tanker without IG P&I → high
# -------------------------------------------------------------------

class TestTankerNoIGPI:

    @pytest.mark.asyncio
    async def test_tanker_no_ig_pi_fires_high(self, rule):
        """A tanker (ship_type 80) without IG P&I should fire high."""
        profile = _profile(ship_type=80, class_society="DNV", pi_tier=None, pi_details=None)
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        # Should have the no_ig_pi_tanker finding
        findings = result.details["findings"]
        checks = [f["check"] for f in findings]
        assert "no_ig_pi_tanker" in checks
        tanker_finding = next(f for f in findings if f["check"] == "no_ig_pi_tanker")
        assert tanker_finding["points"] == 15


# -------------------------------------------------------------------
# Test: Non-IACS classification → moderate
# -------------------------------------------------------------------

class TestNonIACSClassification:

    @pytest.mark.asyncio
    async def test_non_iacs_class_fires_moderate(self, rule):
        """Vessel classed by unknown non-IACS society should fire moderate."""
        profile = _profile(
            ship_type=70,  # cargo, not tanker
            class_society="Panama Maritime Authority",
            pi_tier="IG",
            pi_details={"is_ig_member": True},
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        findings = result.details["findings"]
        checks = [f["check"] for f in findings]
        assert "non_iacs_classification" in checks
        cls_finding = next(f for f in findings if f["check"] == "non_iacs_classification")
        assert cls_finding["severity"] == "moderate"
        assert cls_finding["points"] == 8


# -------------------------------------------------------------------
# Test: Unclassed vessel → critical
# -------------------------------------------------------------------

class TestNoClassification:

    @pytest.mark.asyncio
    async def test_no_class_fires_critical(self, rule):
        """Vessel with no classification society should fire critical."""
        profile = _profile(
            ship_type=80,
            pi_tier="IG",
            pi_details={"is_ig_member": True},
        )
        # Remove class_society to simulate no classification
        profile.pop("class_society", None)
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        findings = result.details["findings"]
        checks = [f["check"] for f in findings]
        assert "no_classification" in checks
        no_cls = next(f for f in findings if f["check"] == "no_classification")
        assert no_cls["severity"] == "critical"
        assert no_cls["points"] == 25


# -------------------------------------------------------------------
# Test: Recent class change to Russian Register → high
# -------------------------------------------------------------------

class TestRecentClassChange:

    @pytest.mark.asyncio
    async def test_class_change_to_russian_register(self, rule):
        """Class changed from DNV to Russian Register 3 months ago → high."""
        profile = _profile(
            ship_type=80,
            class_society="RS",
            pi_tier="IG",
            pi_details={"is_ig_member": True},
            previous_class_society="DNV",
            class_change_date="2026-01-01",
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        findings = result.details["findings"]
        checks = [f["check"] for f in findings]
        # Should have both russian_maritime_register and recent_class_change
        assert "russian_maritime_register" in checks
        assert "recent_class_change" in checks


# -------------------------------------------------------------------
# Test: Properly insured vessel with Lloyd's Register → no firing
# -------------------------------------------------------------------

class TestProperlyInsured:

    @pytest.mark.asyncio
    async def test_proper_insurance_and_class_no_fire(self, rule):
        """Vessel with IG P&I and Lloyd's Register should not fire."""
        profile = _profile(
            ship_type=80,
            class_society="Lloyd's Register",
            pi_tier="IG",
            pi_details={"is_ig_member": True, "provider": "Gard"},
            insurer="Gard",
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_proper_insurance_lr_code_no_fire(self, rule):
        """Vessel with IG P&I and LR code should not fire."""
        profile = _profile(
            ship_type=85,
            class_society="LR",
            pi_tier="IG",
            pi_details={"is_ig_member": True},
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is False


# -------------------------------------------------------------------
# Test: Non-tanker without IG P&I → moderate (not high)
# -------------------------------------------------------------------

class TestNonTankerNoIGPI:

    @pytest.mark.asyncio
    async def test_non_tanker_no_ig_pi_moderate(self, rule):
        """Non-tanker without IG P&I should fire moderate, not high."""
        profile = _profile(
            ship_type=70,  # cargo
            class_society="DNV",
            pi_tier=None,
            pi_details=None,
            insurer=None,
        )
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        findings = result.details["findings"]
        checks = [f["check"] for f in findings]
        assert "no_ig_pi_non_tanker" in checks
        assert "no_ig_pi_tanker" not in checks
        pi_finding = next(f for f in findings if f["check"] == "no_ig_pi_non_tanker")
        assert pi_finding["severity"] == "moderate"
        assert pi_finding["points"] == 8


# -------------------------------------------------------------------
# Test: Combined: no class + no insurance → critical with combined detail
# -------------------------------------------------------------------

class TestCombinedFactors:

    @pytest.mark.asyncio
    async def test_no_class_no_insurance_critical(self, rule):
        """No classification + no insurance should escalate to critical."""
        profile = _profile(
            ship_type=80,
            pi_tier=None,
            pi_details=None,
            insurer=None,
        )
        profile.pop("class_society", None)
        result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "critical"
        findings = result.details["findings"]
        assert len(findings) >= 2
        checks = [f["check"] for f in findings]
        assert "no_classification" in checks
        assert "no_ig_pi_tanker" in checks
        # Combined points should be at least 25 + 15 = 40
        assert result.points >= 40


# -------------------------------------------------------------------
# Test: No profile → None
# -------------------------------------------------------------------

class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_no_profile_returns_none(self, rule):
        """Rule should return None if no profile available."""
        result = await rule.evaluate(123456789, None, [], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_iacs_name_variations(self, rule):
        """Various IACS name formats should be recognized."""
        from rules.insurance_class_risk import _is_iacs

        assert _is_iacs("DNV")[0] is True
        assert _is_iacs("DNV GL")[0] is True
        assert _is_iacs("Det Norske Veritas")[0] is True
        assert _is_iacs("Lloyd's Register")[0] is True
        assert _is_iacs("LR")[0] is True
        assert _is_iacs("ClassNK")[0] is True
        assert _is_iacs("Bureau Veritas")[0] is True
        assert _is_iacs("Unknown Society")[0] is False
        assert _is_iacs(None)[0] is False
        assert _is_iacs("")[0] is False

    @pytest.mark.asyncio
    async def test_russian_register_detected(self, rule):
        """Russian Maritime Register should be flagged specifically."""
        from rules.insurance_class_risk import _is_iacs

        is_iacs, is_russian = _is_iacs("RS")
        assert is_iacs is True
        assert is_russian is True

        is_iacs, is_russian = _is_iacs("Russian Maritime Register")
        assert is_iacs is True
        assert is_russian is True

        # DNV should not be flagged as Russian
        is_iacs, is_russian = _is_iacs("DNV")
        assert is_iacs is True
        assert is_russian is False
