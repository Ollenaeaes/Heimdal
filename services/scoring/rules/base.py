"""Abstract base class for all scoring rules.

Every scoring rule lives in its own module under ``rules/`` and extends
:class:`ScoringRule`.  The engine auto-discovers all concrete subclasses
at startup via ``importlib`` so adding a new rule requires **zero** engine
changes — just drop a new file here.
"""

from __future__ import annotations

import abc
from typing import Any, Optional, Sequence

from shared.models.anomaly import RuleResult


class ScoringRule(abc.ABC):
    """Base class that every scoring rule must extend."""

    @property
    @abc.abstractmethod
    def rule_id(self) -> str:
        """Unique identifier for this rule (must match a key in MAX_PER_RULE)."""
        ...

    @property
    @abc.abstractmethod
    def rule_category(self) -> str:
        """Either ``'gfw_sourced'`` or ``'realtime'``."""
        ...

    @abc.abstractmethod
    async def evaluate(
        self,
        mmsi: int,
        profile: dict[str, Any] | None,
        recent_positions: Sequence[dict[str, Any]],
        existing_anomalies: Sequence[dict[str, Any]],
        gfw_events: Sequence[dict[str, Any]],
    ) -> Optional[RuleResult]:
        """Evaluate this rule for a single vessel.

        Parameters
        ----------
        mmsi:
            The vessel's MMSI.
        profile:
            Row from ``vessel_profiles`` (dict) or *None* if the vessel has
            no profile yet.
        recent_positions:
            Recent rows from ``vessel_positions`` for this MMSI (may be
            empty for GFW-sourced rules).
        existing_anomalies:
            Unresolved anomaly_event rows already recorded for this MMSI.
        gfw_events:
            GFW event rows for this MMSI (may be empty for real-time rules).

        Returns
        -------
        ``RuleResult`` with ``fired=True`` if the rule triggers, or
        ``RuleResult`` with ``fired=False`` / ``None`` otherwise.
        """
        ...
