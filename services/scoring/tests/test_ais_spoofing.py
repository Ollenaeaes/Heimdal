"""Tests for AIS Position Spoofing detection rule."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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
    heading: float = 180.0,
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
        "heading": heading,
        "nav_status": nav_status,
    }
    if draught is not None:
        p["draught"] = draught
    return p


# ===================================================================
# AIS Position Spoofing
# ===================================================================


class TestAisSpoofing:
    """Tests for rules/ais_spoofing.py."""

    @pytest.fixture
    def rule(self):
        from rules.ais_spoofing import AisSpoofingRule
        return AisSpoofingRule()

    # ---------------------------------------------------------------
    # Position jump
    # ---------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_position_jump_1000nm_in_30min(self, rule):
        """1000nm in 30 minutes -> critical spoofing alert."""
        positions = [
            _pos(hours_ago=1.0, lat=55.0, lon=20.0, sog=12.0),
            _pos(hours_ago=0.5, lat=40.0, lon=20.0, sog=12.0),  # ~900nm south
        ]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result.fired is True
        assert result.severity == "critical"
        assert result.points == 30.0
        assert result.details["reason"] == "position_jump"
        assert result.details["distance_nm"] > 500
        assert result.source == "realtime"

    # ---------------------------------------------------------------
    # Circle spoofing
    # ---------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_circle_pattern_fires(self, rule):
        """8 positions over 24h forming a circle with low variance -> circle_spoofing."""
        import math
        center_lat, center_lon = 55.0, 20.0
        radius_deg = 0.05  # small circle
        n_points = 8
        positions = []
        for i in range(n_points):
            angle = 2 * math.pi * i / n_points
            lat = center_lat + radius_deg * math.cos(angle)
            lon = center_lon + radius_deg * math.sin(angle)
            hours_ago = 28.0 - (i * 3.5)  # spread over ~25 hours
            positions.append(
                _pos(hours_ago=hours_ago, lat=lat, lon=lon, sog=5.0, nav_status=0)
            )
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result.fired is True
        assert result.severity == "critical"
        assert result.points == 30.0
        assert result.details["reason"] == "circle_spoofing"

    # ---------------------------------------------------------------
    # Anchor spoofing
    # ---------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_stationary_underway_48h_fires(self, rule):
        """Stationary for 48h with nav_status 'underway' -> anchor_spoofing."""
        positions = [
            _pos(hours_ago=50, lat=55.0000, lon=20.0000, sog=0.0, nav_status=0),
            _pos(hours_ago=40, lat=55.0001, lon=20.0001, sog=0.0, nav_status=0),
            _pos(hours_ago=30, lat=55.0000, lon=20.0000, sog=0.0, nav_status=0),
            _pos(hours_ago=20, lat=55.0001, lon=20.0000, sog=0.0, nav_status=0),
            _pos(hours_ago=10, lat=55.0000, lon=20.0001, sog=0.0, nav_status=0),
            _pos(hours_ago=0, lat=55.0001, lon=20.0001, sog=0.0, nav_status=0),
        ]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result.fired is True
        assert result.severity == "critical"
        assert result.points == 30.0
        assert result.details["reason"] == "anchor_spoofing"

    @pytest.mark.asyncio
    async def test_genuinely_anchored_not_flagged(self, rule):
        """Vessel at anchor with nav_status 'at anchor' -> NOT flagged."""
        positions = [
            _pos(hours_ago=50, lat=55.0000, lon=20.0000, sog=0.0, nav_status=1),
            _pos(hours_ago=40, lat=55.0001, lon=20.0001, sog=0.0, nav_status=1),
            _pos(hours_ago=30, lat=55.0000, lon=20.0000, sog=0.0, nav_status=1),
            _pos(hours_ago=20, lat=55.0001, lon=20.0000, sog=0.0, nav_status=1),
            _pos(hours_ago=10, lat=55.0000, lon=20.0001, sog=0.0, nav_status=1),
            _pos(hours_ago=0, lat=55.0001, lon=20.0001, sog=0.0, nav_status=1),
        ]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result.fired is False

    # ---------------------------------------------------------------
    # GPS drift — should NOT fire
    # ---------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_gps_drift_not_flagged(self, rule):
        """GPS drift (< 0.01 nm variation) -> NOT flagged as spoofing."""
        # Tiny variation around a point, short time span, normal nav_status
        positions = [
            _pos(hours_ago=2, lat=55.00001, lon=20.00001, sog=0.1, nav_status=1),
            _pos(hours_ago=1, lat=55.00002, lon=20.00002, sog=0.1, nav_status=1),
            _pos(hours_ago=0, lat=55.00001, lon=20.00003, sog=0.1, nav_status=1),
        ]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result.fired is False

    # ---------------------------------------------------------------
    # Slow-roll spoofing
    # ---------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_slow_roll_fires(self, rule):
        """0.3 knots, zero heading change for 12h -> slow_roll_spoofing."""
        positions = [
            _pos(hours_ago=13, lat=55.0, lon=20.0, sog=0.3, heading=90.0, nav_status=0),
            _pos(hours_ago=10, lat=55.0, lon=20.0, sog=0.2, heading=90.0, nav_status=0),
            _pos(hours_ago=7, lat=55.0, lon=20.0, sog=0.3, heading=90.0, nav_status=0),
            _pos(hours_ago=4, lat=55.0, lon=20.0, sog=0.3, heading=90.0, nav_status=0),
            _pos(hours_ago=1, lat=55.0, lon=20.0, sog=0.2, heading=90.0, nav_status=0),
            _pos(hours_ago=0, lat=55.0, lon=20.0, sog=0.3, heading=90.0, nav_status=0),
        ]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result.fired is True
        assert result.severity == "critical"
        assert result.points == 30.0
        assert result.details["reason"] == "slow_roll_spoofing"

    # ---------------------------------------------------------------
    # Normal movement — should NOT fire
    # ---------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_normal_movement_not_flagged(self, rule):
        """Normal vessel movement at reasonable speed -> not flagged."""
        positions = [
            _pos(hours_ago=6, lat=55.0, lon=20.0, sog=12.0, heading=180.0),
            _pos(hours_ago=4, lat=54.8, lon=20.1, sog=11.5, heading=175.0),
            _pos(hours_ago=2, lat=54.6, lon=20.2, sog=12.5, heading=185.0),
            _pos(hours_ago=0, lat=54.4, lon=20.3, sog=11.0, heading=178.0),
        ]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result.fired is False

    # ---------------------------------------------------------------
    # Edge cases
    # ---------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_insufficient_positions_returns_none(self, rule):
        """Less than 2 positions -> None."""
        positions = [_pos(hours_ago=1)]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result is None

    @pytest.mark.asyncio
    async def test_rule_id_and_category(self, rule):
        assert rule.rule_id == "ais_spoofing"
        assert rule.rule_category == "realtime"

    @pytest.mark.asyncio
    async def test_source_is_realtime(self, rule):
        """Fired results must have source='realtime'."""
        positions = [
            _pos(hours_ago=1.0, lat=55.0, lon=20.0, sog=12.0),
            _pos(hours_ago=0.5, lat=40.0, lon=20.0, sog=12.0),
        ]
        result = await rule.evaluate(123456789, {}, positions, [], [])
        assert result.fired is True
        assert result.source == "realtime"
