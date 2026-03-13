"""Tests for the ownership_risk scoring rule."""

from __future__ import annotations

import json
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

_NOW = datetime(2026, 3, 12, 12, 0, 0, tzinfo=timezone.utc)


def _days_ago(days: int) -> str:
    """Return ISO date string for N days ago."""
    return (_NOW - timedelta(days=days)).isoformat()


class TestOwnershipRisk:
    """Tests for rules/ownership_risk.py."""

    @pytest.fixture
    def rule(self):
        from rules.ownership_risk import OwnershipRiskRule
        return OwnershipRiskRule()

    @pytest.mark.asyncio
    async def test_single_vessel_company_fires_moderate(self, rule):
        """Owner with fleet_size=1 → moderate ownership_risk."""
        profile = {
            "ownership_data": {
                "owners": [
                    {"name": "Oceanic Holdings Ltd", "country": "NL", "role": "owner", "fleet_size": 1, "incorporated_date": None}
                ],
                "single_vessel_company": True,
                "ownership_status": "verified",
                "history": [],
            }
        }
        with patch("rules.ownership_risk._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "moderate"
        assert result.points == 8.0
        assert result.details["factor"] == "single_vessel_company"

    @pytest.mark.asyncio
    async def test_recently_incorporated_fires_moderate(self, rule):
        """Company incorporated 6 months ago → moderate ownership_risk."""
        profile = {
            "ownership_data": {
                "owners": [
                    {
                        "name": "New Maritime Corp",
                        "country": "NL",
                        "role": "owner",
                        "fleet_size": 5,
                        "incorporated_date": _days_ago(180),
                    }
                ],
                "single_vessel_company": False,
                "ownership_status": "verified",
                "history": [],
            }
        }
        with patch("rules.ownership_risk._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "moderate"
        assert result.points == 8.0
        assert result.details["factor"] == "recently_incorporated"

    @pytest.mark.asyncio
    async def test_high_risk_jurisdiction_tanker_fires_high(self, rule):
        """Cameroon-registered owner for a tanker → high ownership_risk."""
        profile = {
            "ship_type": 80,
            "ownership_data": {
                "owners": [
                    {"name": "Douala Shipping SA", "country": "CM", "role": "owner", "fleet_size": 3, "incorporated_date": _days_ago(1000)}
                ],
                "single_vessel_company": False,
                "ownership_status": "verified",
                "history": [],
            },
        }
        with patch("rules.ownership_risk._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 15.0
        assert result.details["factor"] == "high_risk_jurisdiction"

    @pytest.mark.asyncio
    async def test_frequent_ownership_changes_fires_high(self, rule):
        """2 ownership changes in 8 months → high ownership_risk."""
        profile = {
            "ownership_data": {
                "owners": [
                    {"name": "Current Owner LLC", "country": "GR", "role": "owner", "fleet_size": 10, "incorporated_date": _days_ago(2000)}
                ],
                "single_vessel_company": False,
                "ownership_status": "verified",
                "history": [
                    {"date": _days_ago(90), "change": "owner_changed", "from": "Previous Co", "to": "Current Owner LLC"},
                    {"date": _days_ago(240), "change": "owner_changed", "from": "Original Co", "to": "Previous Co"},
                ],
            },
        }
        with patch("rules.ownership_risk._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "high"
        assert result.points == 15.0
        assert result.details["factor"] == "frequent_ownership_changes"

    @pytest.mark.asyncio
    async def test_no_ownership_data_not_enriched_does_not_fire(self, rule):
        """No ownership data and no enrichment yet → don't penalise."""
        profile = {
            "ownership_data": None,
        }
        with patch("rules.ownership_risk._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_no_ownership_data_with_basic_owner_does_not_fire(self, rule):
        """No enrichment data but registered_owner exists → don't fire."""
        profile = {
            "ownership_data": None,
            "registered_owner": "ARCTIC ORANGE LNG C/O: OSK SHIPPING LTD",
        }
        with patch("rules.ownership_risk._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_no_ownership_data_enriched_fires_opaque(self, rule):
        """No ownership data after enrichment attempted → opaque_ownership."""
        profile = {
            "ownership_data": None,
            "enriched_at": "2026-03-12T10:00:00+00:00",
        }
        with patch("rules.ownership_risk._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "moderate"
        assert result.points == 8.0
        assert result.details["factor"] == "opaque_ownership"

    @pytest.mark.asyncio
    async def test_combined_factors_escalate_to_critical(self, rule):
        """Single-vessel + recently incorporated + high-risk jurisdiction → critical (combined)."""
        profile = {
            "ship_type": 85,  # tanker
            "ownership_data": {
                "owners": [
                    {
                        "name": "Shadow Fleet Ltd",
                        "country": "TG",  # Togo — high risk
                        "role": "owner",
                        "fleet_size": 1,
                        "incorporated_date": _days_ago(120),  # 4 months ago
                    }
                ],
                "single_vessel_company": True,
                "ownership_status": "verified",
                "history": [],
            },
        }
        with patch("rules.ownership_risk._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "critical"
        assert result.points == 25.0
        assert result.details["factor_count"] >= 2
        assert "single_vessel_company" in result.details["factors"]
        assert "recently_incorporated" in result.details["factors"]
        assert "high_risk_jurisdiction" in result.details["factors"]

    @pytest.mark.asyncio
    async def test_normal_vessel_established_owner_no_fire(self, rule):
        """Normal vessel with established owner in Netherlands → no firing."""
        profile = {
            "ship_type": 70,  # bulk carrier
            "ownership_data": {
                "owners": [
                    {
                        "name": "Rotterdam Maritime BV",
                        "country": "NL",
                        "role": "owner",
                        "fleet_size": 25,
                        "incorporated_date": _days_ago(3650),  # 10 years ago
                    }
                ],
                "single_vessel_company": False,
                "ownership_status": "verified",
                "history": [],
            },
        }
        with patch("rules.ownership_risk._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_non_tanker_high_risk_jurisdiction_fires_moderate(self, rule):
        """Non-tanker with high-risk jurisdiction → moderate (not high)."""
        profile = {
            "ship_type": 70,  # bulk carrier, not tanker
            "ownership_data": {
                "owners": [
                    {
                        "name": "Libreville Cargo SA",
                        "country": "GA",  # Gabon — high risk
                        "role": "owner",
                        "fleet_size": 8,
                        "incorporated_date": _days_ago(2000),
                    }
                ],
                "single_vessel_company": False,
                "ownership_status": "verified",
                "history": [],
            },
        }
        with patch("rules.ownership_risk._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "moderate"
        assert result.points == 8.0
        assert result.details["factor"] == "high_risk_jurisdiction"

    @pytest.mark.asyncio
    async def test_ownership_data_as_json_string(self, rule):
        """ownership_data stored as JSON string → parsed correctly."""
        ownership_dict = {
            "owners": [
                {"name": "String Data Corp", "country": "NL", "role": "owner", "fleet_size": 1, "incorporated_date": None}
            ],
            "single_vessel_company": True,
            "ownership_status": "verified",
            "history": [],
        }
        profile = {
            "ownership_data": json.dumps(ownership_dict),
        }
        with patch("rules.ownership_risk._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.severity == "moderate"
        assert result.points == 8.0
        assert result.details["factor"] == "single_vessel_company"

    @pytest.mark.asyncio
    async def test_no_profile_returns_none(self, rule):
        """No profile at all → None."""
        result = await rule.evaluate(123456789, None, [], [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_source_is_realtime(self, rule):
        """Fired result should have source='realtime'."""
        profile = {"ownership_data": None, "enriched_at": "2026-03-12T10:00:00+00:00"}
        with patch("rules.ownership_risk._utcnow", return_value=_NOW):
            result = await rule.evaluate(123456789, profile, [], [], [])
        assert result.fired is True
        assert result.source == "realtime"
