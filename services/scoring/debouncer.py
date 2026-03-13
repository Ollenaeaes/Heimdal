"""Scoring debouncer: rate-limits position-triggered evaluations.

Ensures the scoring engine evaluates each vessel at most once per debounce
window (default 60 s, 30 s for red-tier vessels). The first position for
a previously-unseen vessel triggers an immediate evaluation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("scoring.debouncer")


class ScoringDebouncer:
    """Debounce position updates before scoring evaluation.

    Parameters
    ----------
    engine:
        A :class:`ScoringEngine` (or compatible mock) with an async
        ``evaluate_realtime(mmsi)`` method.
    default_seconds:
        Debounce window for non-red vessels.
    red_tier_seconds:
        Debounce window for red-tier vessels.
    max_concurrent:
        Maximum number of concurrent evaluations.
    """

    def __init__(
        self,
        engine: Any,
        *,
        default_seconds: float = 60.0,
        red_tier_seconds: float = 30.0,
        max_concurrent: int = 10,
    ) -> None:
        self.engine = engine
        self.default_seconds = default_seconds
        self.red_tier_seconds = red_tier_seconds
        self.max_concurrent = max_concurrent

        self._pending: dict[int, asyncio.TimerHandle] = {}
        self._known_mmsis: set[int] = set()
        self._red_mmsis: set[int] = set()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._eval_count: int = 0  # counter for testing / observability

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def on_position(self, mmsi: int) -> None:
        """Handle a new position update for a vessel.

        * First position for a new MMSI -> immediate evaluation.
        * Subsequent positions -> debounced (timer resets on each call).
        """
        loop = asyncio.get_running_loop()

        # Cancel any existing pending timer for this vessel
        existing = self._pending.pop(mmsi, None)
        if existing is not None:
            existing.cancel()

        # First time seeing this vessel -> immediate evaluation
        if mmsi not in self._known_mmsis:
            self._known_mmsis.add(mmsi)
            await self._evaluate(mmsi)
            return

        # Schedule deferred evaluation after debounce window
        seconds = (
            self.red_tier_seconds
            if mmsi in self._red_mmsis
            else self.default_seconds
        )
        handle = loop.call_later(
            seconds,
            lambda m=mmsi: asyncio.ensure_future(self._evaluate(m)),
        )
        self._pending[mmsi] = handle

    def update_red_mmsis(self, mmsi: int, tier: str) -> None:
        """Update the set of red-tier MMSIs for debounce interval selection."""
        if tier == "red":
            self._red_mmsis.add(mmsi)
        else:
            self._red_mmsis.discard(mmsi)

    @property
    def eval_count(self) -> int:
        """Number of evaluations that have been executed (for testing)."""
        return self._eval_count

    @property
    def pending_count(self) -> int:
        """Number of vessels with pending (scheduled) evaluations."""
        return len(self._pending)

    def shutdown(self) -> None:
        """Cancel all pending timers (for clean shutdown)."""
        for handle in self._pending.values():
            handle.cancel()
        self._pending.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _evaluate(self, mmsi: int) -> None:
        """Run scoring evaluation for a single vessel."""
        self._pending.pop(mmsi, None)
        async with self._semaphore:
            try:
                await self.engine.evaluate_realtime(mmsi)
                self._eval_count += 1
                logger.debug("Debounced evaluation completed for MMSI %d", mmsi)
            except Exception:
                logger.exception("Debounced evaluation failed for MMSI %d", mmsi)
