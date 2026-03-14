"""Tests for services/scoring/network_scorer.py.

Verifies:
- Isolated vessel gets score 0
- 1-hop from sanctioned vessel: 30 points
- 2-hop from sanctioned vessel: 15 points
- 3+ hop: 5 points per sanctioned vessel
- Pattern bonus with >= 3 qualifying vessels
- recalculate_cluster_scores processes all cluster members
- Score is stored in vessel_profiles
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from services.scoring.network_scorer import (
    calculate_network_score,
    recalculate_cluster_scores,
    _get_sanctioned_mmsis,
    _get_pattern_vessels,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_score_session(store_calls: list | None = None):
    """Create a session mock that tracks score storage calls."""
    session = AsyncMock()
    store_calls = store_calls if store_calls is not None else []

    async def mock_execute(sql_text, params=None, *args, **kwargs):
        sql_str = str(sql_text.text) if hasattr(sql_text, 'text') else str(sql_text)
        result_mock = MagicMock()

        if "UPDATE vessel_profiles" in sql_str and "network_score" in sql_str:
            if params:
                store_calls.append(params)

        result_mock.all.return_value = []
        result_mock.first.return_value = None
        return result_mock

    session.execute = mock_execute
    return session


# ---------------------------------------------------------------------------
# Isolated Vessel
# ---------------------------------------------------------------------------


class TestCalculateNetworkScoreIsolated:
    @pytest.mark.asyncio
    @patch("services.scoring.network_scorer.get_network_cluster")
    async def test_isolated_vessel_gets_zero(self, mock_cluster):
        mock_cluster.return_value = {100}
        store_calls = []
        session = _make_score_session(store_calls)

        score = await calculate_network_score(session, 100)
        assert score == 0
        assert len(store_calls) == 1
        assert store_calls[0]["score"] == 0
        assert store_calls[0]["mmsi"] == 100


# ---------------------------------------------------------------------------
# Hop Decay Scoring
# ---------------------------------------------------------------------------


class TestHopDecayScoring:
    @pytest.mark.asyncio
    @patch("services.scoring.network_scorer._get_pattern_vessels")
    @patch("services.scoring.network_scorer._get_sanctioned_mmsis")
    @patch("services.scoring.network_scorer.get_connected_vessels")
    @patch("services.scoring.network_scorer.get_network_cluster")
    async def test_one_hop_from_sanctioned(
        self, mock_cluster, mock_connected, mock_sanctioned, mock_pattern
    ):
        """1 hop from sanctioned vessel = 30 points."""
        mock_cluster.return_value = {100, 200}
        mock_connected.side_effect = lambda s, m: {200} if m == 100 else {100}
        mock_sanctioned.return_value = {200}
        mock_pattern.return_value = set()

        store_calls = []
        session = _make_score_session(store_calls)

        score = await calculate_network_score(session, 100)
        assert score == 30

    @pytest.mark.asyncio
    @patch("services.scoring.network_scorer._get_pattern_vessels")
    @patch("services.scoring.network_scorer._get_sanctioned_mmsis")
    @patch("services.scoring.network_scorer.get_connected_vessels")
    @patch("services.scoring.network_scorer.get_network_cluster")
    async def test_two_hops_from_sanctioned(
        self, mock_cluster, mock_connected, mock_sanctioned, mock_pattern
    ):
        """2 hops from sanctioned vessel = 15 points."""
        mock_cluster.return_value = {100, 200, 300}

        def connected_side_effect(s, m):
            neighbors = {100: {200}, 200: {100, 300}, 300: {200}}
            return neighbors.get(m, set())

        mock_connected.side_effect = connected_side_effect
        mock_sanctioned.return_value = {300}  # 300 is sanctioned, 2 hops from 100
        mock_pattern.return_value = set()

        store_calls = []
        session = _make_score_session(store_calls)

        score = await calculate_network_score(session, 100)
        assert score == 15

    @pytest.mark.asyncio
    @patch("services.scoring.network_scorer._get_pattern_vessels")
    @patch("services.scoring.network_scorer._get_sanctioned_mmsis")
    @patch("services.scoring.network_scorer.get_connected_vessels")
    @patch("services.scoring.network_scorer.get_network_cluster")
    async def test_three_plus_hops_from_sanctioned(
        self, mock_cluster, mock_connected, mock_sanctioned, mock_pattern
    ):
        """3+ hops from sanctioned vessel = 5 points."""
        mock_cluster.return_value = {100, 200, 300, 400}

        def connected_side_effect(s, m):
            neighbors = {100: {200}, 200: {100, 300}, 300: {200, 400}, 400: {300}}
            return neighbors.get(m, set())

        mock_connected.side_effect = connected_side_effect
        mock_sanctioned.return_value = {400}  # 400 is sanctioned, 3 hops from 100
        mock_pattern.return_value = set()

        store_calls = []
        session = _make_score_session(store_calls)

        score = await calculate_network_score(session, 100)
        assert score == 5

    @pytest.mark.asyncio
    @patch("services.scoring.network_scorer._get_pattern_vessels")
    @patch("services.scoring.network_scorer._get_sanctioned_mmsis")
    @patch("services.scoring.network_scorer.get_connected_vessels")
    @patch("services.scoring.network_scorer.get_network_cluster")
    async def test_multiple_sanctioned_vessels(
        self, mock_cluster, mock_connected, mock_sanctioned, mock_pattern
    ):
        """Multiple sanctioned at different hops: sum of points."""
        mock_cluster.return_value = {100, 200, 300}

        def connected_side_effect(s, m):
            neighbors = {100: {200, 300}, 200: {100}, 300: {100}}
            return neighbors.get(m, set())

        mock_connected.side_effect = connected_side_effect
        mock_sanctioned.return_value = {200, 300}  # Both 1 hop away
        mock_pattern.return_value = set()

        store_calls = []
        session = _make_score_session(store_calls)

        score = await calculate_network_score(session, 100)
        assert score == 60  # 30 + 30


# ---------------------------------------------------------------------------
# Pattern Bonus
# ---------------------------------------------------------------------------


class TestPatternBonus:
    @pytest.mark.asyncio
    @patch("services.scoring.network_scorer._get_pattern_vessels")
    @patch("services.scoring.network_scorer._get_sanctioned_mmsis")
    @patch("services.scoring.network_scorer.get_connected_vessels")
    @patch("services.scoring.network_scorer.get_network_cluster")
    async def test_pattern_bonus_with_three_vessels(
        self, mock_cluster, mock_connected, mock_sanctioned, mock_pattern
    ):
        """Cluster with >= 3 pattern vessels gets bonus."""
        mock_cluster.return_value = {100, 200, 300, 400}

        def connected_side_effect(s, m):
            return {100, 200, 300, 400} - {m}

        mock_connected.side_effect = connected_side_effect
        mock_sanctioned.return_value = set()  # No sanctioned
        mock_pattern.return_value = {200, 300, 400}  # 3 pattern vessels

        store_calls = []
        session = _make_score_session(store_calls)

        score = await calculate_network_score(session, 100)
        assert score == 60  # 3 * 20

    @pytest.mark.asyncio
    @patch("services.scoring.network_scorer._get_pattern_vessels")
    @patch("services.scoring.network_scorer._get_sanctioned_mmsis")
    @patch("services.scoring.network_scorer.get_connected_vessels")
    @patch("services.scoring.network_scorer.get_network_cluster")
    async def test_no_pattern_bonus_with_two_vessels(
        self, mock_cluster, mock_connected, mock_sanctioned, mock_pattern
    ):
        """Cluster with < 3 pattern vessels gets no bonus."""
        mock_cluster.return_value = {100, 200, 300}

        def connected_side_effect(s, m):
            return {100, 200, 300} - {m}

        mock_connected.side_effect = connected_side_effect
        mock_sanctioned.return_value = set()
        mock_pattern.return_value = {200, 300}  # Only 2

        store_calls = []
        session = _make_score_session(store_calls)

        score = await calculate_network_score(session, 100)
        assert score == 0

    @pytest.mark.asyncio
    @patch("services.scoring.network_scorer._get_pattern_vessels")
    @patch("services.scoring.network_scorer._get_sanctioned_mmsis")
    @patch("services.scoring.network_scorer.get_connected_vessels")
    @patch("services.scoring.network_scorer.get_network_cluster")
    async def test_combined_hop_and_pattern_score(
        self, mock_cluster, mock_connected, mock_sanctioned, mock_pattern
    ):
        """Hop score + pattern bonus are additive."""
        mock_cluster.return_value = {100, 200, 300, 400, 500}

        def connected_side_effect(s, m):
            neighbors = {
                100: {200},
                200: {100, 300, 400, 500},
                300: {200},
                400: {200},
                500: {200},
            }
            return neighbors.get(m, set())

        mock_connected.side_effect = connected_side_effect
        mock_sanctioned.return_value = {200}  # 1 hop: 30 points
        mock_pattern.return_value = {300, 400, 500}  # 3 pattern: 60 points

        store_calls = []
        session = _make_score_session(store_calls)

        score = await calculate_network_score(session, 100)
        assert score == 90  # 30 + 60


# ---------------------------------------------------------------------------
# Recalculate Cluster Scores
# ---------------------------------------------------------------------------


class TestRecalculateClusterScores:
    @pytest.mark.asyncio
    @patch("services.scoring.network_scorer.calculate_network_score")
    @patch("services.scoring.network_scorer.get_network_cluster")
    async def test_recalculates_all_cluster_members(self, mock_cluster, mock_calc):
        mock_cluster.return_value = {100, 200, 300}
        mock_calc.side_effect = [10, 20, 30]

        session = AsyncMock()
        scores = await recalculate_cluster_scores(session, 100)

        assert len(scores) == 3
        assert mock_calc.call_count == 3
