"""Tests for infrastructure corridor spatial helpers.

Tests the pure-Python functions directly and mocks DB-dependent ones.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.scoring.rules.infra_helpers import (
    angle_difference,
    compute_cable_bearing,
    is_in_infrastructure_corridor,
    is_in_port_approach,
)


# ---------------------------------------------------------------------------
# angle_difference — pure function, no mocking needed
# ---------------------------------------------------------------------------


class TestAngleDifference:
    """Test the minimum angular difference function."""

    def test_same_direction(self):
        assert angle_difference(90.0, 90.0) == 0.0

    def test_opposite_directions(self):
        assert angle_difference(0.0, 180.0) == 180.0

    def test_right_angle(self):
        assert angle_difference(0.0, 90.0) == 90.0

    def test_wraparound_small(self):
        """350 vs 10 degrees should be 20, not 340."""
        assert angle_difference(350.0, 10.0) == 20.0

    def test_wraparound_reverse(self):
        """10 vs 350 degrees should also be 20."""
        assert angle_difference(10.0, 350.0) == 20.0

    def test_near_zero_crossing(self):
        assert angle_difference(5.0, 355.0) == 10.0

    def test_exact_180(self):
        assert angle_difference(90.0, 270.0) == 180.0

    def test_close_angles(self):
        diff = angle_difference(45.0, 50.0)
        assert diff == pytest.approx(5.0)

    def test_large_cog_values(self):
        """Values > 360 should still work due to modulo."""
        diff = angle_difference(370.0, 10.0)
        assert diff == pytest.approx(0.0)

    def test_bearing_aligned_both_ways(self):
        """Cable runs at 45 degrees; vessel at 225 is also aligned (opposite direction)."""
        # With our simple min-angle function, 225 vs 45 = 180
        # The rule layer handles the "either direction" check
        assert angle_difference(225.0, 45.0) == 180.0

    def test_small_alignment(self):
        """15 degrees off cable bearing."""
        assert angle_difference(60.0, 45.0) == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# is_in_infrastructure_corridor — DB queries
# ---------------------------------------------------------------------------


class TestIsInInfrastructureCorridor:
    """Test the corridor proximity check with mocked DB."""

    @pytest.mark.asyncio
    async def test_returns_matches(self):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (1, "NordBalt HVDC Cable", "power_cable", "Svenska Kraftnät", 1.0, {}),
        ]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        routes = await is_in_infrastructure_corridor(mock_session, 56.0, 19.5)
        assert len(routes) == 1
        assert routes[0]["name"] == "NordBalt HVDC Cable"
        assert routes[0]["route_type"] == "power_cable"
        assert routes[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_match(self):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        routes = await is_in_infrastructure_corridor(mock_session, 40.0, 0.0)
        assert routes == []

    @pytest.mark.asyncio
    async def test_returns_multiple_routes(self):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (1, "Cable A", "telecom_cable", None, 1.5, {}),
            (2, "Pipeline B", "gas_pipeline", "GasOp", 2.0, {"note": "x"}),
        ]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        routes = await is_in_infrastructure_corridor(mock_session, 59.0, 25.0)
        assert len(routes) == 2
        assert routes[1]["route_type"] == "gas_pipeline"


# ---------------------------------------------------------------------------
# compute_cable_bearing — DB queries
# ---------------------------------------------------------------------------


class TestComputeCableBearing:
    """Test cable bearing computation with mocked DB."""

    @pytest.mark.asyncio
    async def test_returns_bearing(self):
        # Simulate two points roughly east-west
        mock_result = MagicMock()
        mock_result.first.return_value = (10.0, 55.0, 11.0, 55.0)
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        bearing = await compute_cable_bearing(mock_session, 55.0, 10.5, 1)
        assert bearing is not None
        # East-west should be roughly 90 degrees
        assert 85 < bearing < 95

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_route(self):
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        bearing = await compute_cable_bearing(mock_session, 55.0, 10.5, 999)
        assert bearing is None

    @pytest.mark.asyncio
    async def test_north_south_bearing(self):
        mock_result = MagicMock()
        # Two points roughly north-south
        mock_result.first.return_value = (20.0, 55.0, 20.0, 56.0)
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        bearing = await compute_cable_bearing(mock_session, 55.5, 20.0, 2)
        assert bearing is not None
        # North-south should be roughly 0 degrees
        assert bearing < 5 or bearing > 355


# ---------------------------------------------------------------------------
# is_in_port_approach — delegates to zone_helpers
# ---------------------------------------------------------------------------


class TestIsInPortApproach:
    """Test port approach zone check."""

    @pytest.mark.asyncio
    async def test_in_port_approach(self):
        with patch(
            "services.scoring.rules.zone_helpers.is_near_port",
            new_callable=AsyncMock,
            return_value="Gothenburg",
        ):
            result = await is_in_port_approach(AsyncMock(), 57.71, 11.97)
            assert result is True

    @pytest.mark.asyncio
    async def test_not_in_port_approach(self):
        with patch(
            "services.scoring.rules.zone_helpers.is_near_port",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await is_in_port_approach(AsyncMock(), 56.0, 19.0)
            assert result is False
