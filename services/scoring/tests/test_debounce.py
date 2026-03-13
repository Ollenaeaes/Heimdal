"""Tests for the scoring debouncer.

Verifies that position-triggered evaluations are debounced so the scoring
engine evaluates each vessel at most once per debounce window.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# Make the scoring service importable
_scoring_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scoring_dir))
sys.path.insert(0, str(_scoring_dir.parent.parent))

from debouncer import ScoringDebouncer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine() -> AsyncMock:
    """Return a mock engine with an async evaluate_realtime method."""
    engine = AsyncMock()
    engine.evaluate_realtime = AsyncMock(return_value=[])
    return engine


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_vessel_immediate_evaluation():
    """First position for a new MMSI triggers immediate evaluation."""
    engine = _make_engine()
    debouncer = ScoringDebouncer(engine, default_seconds=60, red_tier_seconds=30)

    await debouncer.on_position(123456789)

    engine.evaluate_realtime.assert_awaited_once_with(123456789)
    assert debouncer.eval_count == 1


@pytest.mark.asyncio
async def test_20_positions_in_60s_produces_1_evaluation():
    """Rapid position updates within the debounce window produce only one
    evaluation (the initial one), plus one deferred evaluation after the
    timer fires."""
    engine = _make_engine()
    debouncer = ScoringDebouncer(engine, default_seconds=0.1, red_tier_seconds=0.05)

    # First call -> immediate
    await debouncer.on_position(111111111)
    assert debouncer.eval_count == 1

    # 19 more calls within the window — each resets the timer
    for _ in range(19):
        await debouncer.on_position(111111111)

    # Only the initial evaluation so far
    assert debouncer.eval_count == 1

    # Wait for the debounce timer to fire (0.1s + margin)
    await asyncio.sleep(0.2)

    # Now we should have exactly 2: 1 immediate + 1 debounced
    assert debouncer.eval_count == 2
    assert engine.evaluate_realtime.await_count == 2


@pytest.mark.asyncio
async def test_debounce_timer_resets_on_new_position():
    """Each new position resets the debounce timer, delaying evaluation."""
    engine = _make_engine()
    debouncer = ScoringDebouncer(engine, default_seconds=0.15, red_tier_seconds=0.1)

    # First call -> immediate
    await debouncer.on_position(222222222)
    assert debouncer.eval_count == 1

    # Send positions at 0.05s intervals (should keep resetting the timer)
    for _ in range(4):
        await asyncio.sleep(0.05)
        await debouncer.on_position(222222222)

    # Still only the initial evaluation (timer keeps resetting)
    assert debouncer.eval_count == 1

    # Wait for the debounce window (0.15s) after the last position
    await asyncio.sleep(0.25)

    # Now the deferred evaluation should have fired
    assert debouncer.eval_count == 2


@pytest.mark.asyncio
async def test_red_vessel_30s_debounce():
    """Red-tier vessels use the shorter debounce interval."""
    engine = _make_engine()
    debouncer = ScoringDebouncer(engine, default_seconds=1.0, red_tier_seconds=0.1)

    # Mark vessel as red
    debouncer.update_red_mmsis(333333333, "red")

    # First call -> immediate
    await debouncer.on_position(333333333)
    assert debouncer.eval_count == 1

    # Second position -> debounced
    await debouncer.on_position(333333333)
    assert debouncer.eval_count == 1

    # Wait for the red tier debounce (0.1s) — should fire before default (1.0s)
    await asyncio.sleep(0.2)
    assert debouncer.eval_count == 2


@pytest.mark.asyncio
async def test_red_vessel_promoted_to_green_uses_default():
    """When a vessel is no longer red, it uses the default debounce."""
    engine = _make_engine()
    debouncer = ScoringDebouncer(engine, default_seconds=0.3, red_tier_seconds=0.05)

    # First position as red -> immediate
    debouncer.update_red_mmsis(444444444, "red")
    await debouncer.on_position(444444444)
    assert debouncer.eval_count == 1

    # Change to green
    debouncer.update_red_mmsis(444444444, "green")

    # Send another position
    await debouncer.on_position(444444444)

    # Wait for the red interval — should NOT have fired because vessel is green now
    await asyncio.sleep(0.1)
    assert debouncer.eval_count == 1

    # Wait for the default interval
    await asyncio.sleep(0.3)
    assert debouncer.eval_count == 2


@pytest.mark.asyncio
async def test_concurrent_batch_evaluation():
    """Multiple vessels can be evaluated concurrently up to the semaphore limit."""
    engine = _make_engine()
    # Use a small concurrency limit
    debouncer = ScoringDebouncer(engine, default_seconds=0.05, max_concurrent=3)

    # Send first positions for 5 vessels (all should get immediate evaluation)
    for mmsi in range(100000001, 100000006):
        await debouncer.on_position(mmsi)

    assert debouncer.eval_count == 5
    assert engine.evaluate_realtime.await_count == 5


@pytest.mark.asyncio
async def test_concurrent_batch_with_debounce():
    """Debounced evaluations for multiple vessels fire concurrently."""
    engine = _make_engine()
    debouncer = ScoringDebouncer(engine, default_seconds=0.1, max_concurrent=5)

    # Initial positions for 3 vessels
    for mmsi in [200000001, 200000002, 200000003]:
        await debouncer.on_position(mmsi)
    assert debouncer.eval_count == 3

    # Second positions for all 3 -> debounced
    for mmsi in [200000001, 200000002, 200000003]:
        await debouncer.on_position(mmsi)
    assert debouncer.eval_count == 3

    # Wait for debounce timers
    await asyncio.sleep(0.2)

    # All 3 deferred evaluations should have fired
    assert debouncer.eval_count == 6


@pytest.mark.asyncio
async def test_configurable_debounce_interval():
    """The debounce interval is configurable via constructor parameters."""
    engine = _make_engine()

    # Very short interval
    debouncer = ScoringDebouncer(engine, default_seconds=0.05, red_tier_seconds=0.02)

    await debouncer.on_position(555555555)
    await debouncer.on_position(555555555)  # debounced
    assert debouncer.eval_count == 1

    await asyncio.sleep(0.1)
    assert debouncer.eval_count == 2

    # Now with a longer interval
    engine2 = _make_engine()
    debouncer2 = ScoringDebouncer(engine2, default_seconds=0.5, red_tier_seconds=0.25)

    await debouncer2.on_position(666666666)
    await debouncer2.on_position(666666666)  # debounced
    assert debouncer2.eval_count == 1

    # After 0.1s, should NOT have fired (0.5s window)
    await asyncio.sleep(0.1)
    assert debouncer2.eval_count == 1

    # Clean up
    debouncer2.shutdown()


@pytest.mark.asyncio
async def test_evaluation_failure_does_not_crash():
    """An exception in evaluate_realtime should be caught and logged."""
    engine = _make_engine()
    engine.evaluate_realtime.side_effect = RuntimeError("DB connection lost")

    debouncer = ScoringDebouncer(engine, default_seconds=0.05)

    # First position -> immediate evaluation that fails
    await debouncer.on_position(777777777)
    # eval_count does NOT increment on failure
    assert debouncer.eval_count == 0

    # Second position -> debounced, also fails
    await debouncer.on_position(777777777)
    await asyncio.sleep(0.1)
    assert debouncer.eval_count == 0

    # Engine was called twice
    assert engine.evaluate_realtime.await_count == 2


@pytest.mark.asyncio
async def test_shutdown_cancels_pending_timers():
    """shutdown() cancels all pending debounce timers."""
    engine = _make_engine()
    debouncer = ScoringDebouncer(engine, default_seconds=1.0)

    # Create initial + pending for 2 vessels
    await debouncer.on_position(888888881)
    await debouncer.on_position(888888882)
    await debouncer.on_position(888888881)  # now pending
    await debouncer.on_position(888888882)  # now pending

    assert debouncer.pending_count == 2
    assert debouncer.eval_count == 2  # 2 initial

    debouncer.shutdown()
    assert debouncer.pending_count == 0

    # Wait — nothing should fire
    await asyncio.sleep(0.1)
    assert debouncer.eval_count == 2


@pytest.mark.asyncio
async def test_multiple_vessels_independent_debounce():
    """Each vessel has its own independent debounce timer."""
    engine = _make_engine()
    debouncer = ScoringDebouncer(engine, default_seconds=0.1)

    # First positions for 2 vessels
    await debouncer.on_position(900000001)
    await debouncer.on_position(900000002)
    assert debouncer.eval_count == 2

    # Second position for vessel 1 only
    await debouncer.on_position(900000001)

    # Wait for debounce
    await asyncio.sleep(0.2)

    # Vessel 1 got a deferred evaluation, vessel 2 did not
    assert debouncer.eval_count == 3
    # Check the calls: initial 900000001, initial 900000002, deferred 900000001
    calls = [c.args[0] for c in engine.evaluate_realtime.await_args_list]
    assert calls == [900000001, 900000002, 900000001]
