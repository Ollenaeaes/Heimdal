"""Scoring engine: auto-discovers rules, evaluates them, persists anomalies.

The engine subscribes to two Redis pub/sub channels:

- ``heimdal:positions`` — triggers real-time rule evaluation
- ``heimdal:enrichment_complete`` — triggers GFW-sourced rule evaluation
"""

from __future__ import annotations

import importlib
import inspect
import json
import logging
import pkgutil
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from shared.db.connection import get_session
from shared.db.repositories import (
    create_anomaly_event,
    get_vessel_profile_by_mmsi,
    get_vessel_track,
    list_anomaly_events_by_mmsi,
    list_gfw_events_by_mmsi,
)
from shared.models.anomaly import RuleResult

from rules.base import ScoringRule

logger = logging.getLogger("scoring.engine")


# ---------------------------------------------------------------------------
# Rule discovery
# ---------------------------------------------------------------------------


def discover_rules() -> list[ScoringRule]:
    """Import every module inside the ``rules`` package and return instances
    of all concrete :class:`ScoringRule` subclasses found."""
    import rules as rules_pkg

    rule_instances: list[ScoringRule] = []
    seen_classes: set[type] = set()

    for importer, modname, ispkg in pkgutil.walk_packages(
        rules_pkg.__path__, prefix=rules_pkg.__name__ + "."
    ):
        if ispkg:
            continue
        try:
            module = importlib.import_module(modname)
        except Exception:
            logger.exception("Failed to import rule module %s", modname)
            continue

        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, ScoringRule)
                and obj is not ScoringRule
                and not inspect.isabstract(obj)
                and obj not in seen_classes
            ):
                seen_classes.add(obj)
                rule_instances.append(obj())

    logger.info(
        "Discovered %d scoring rules: %s",
        len(rule_instances),
        [r.rule_id for r in rule_instances],
    )
    return rule_instances


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ScoringEngine:
    """Orchestrates rule evaluation for vessels."""

    def __init__(self, rules: list[ScoringRule] | None = None) -> None:
        self.rules: list[ScoringRule] = rules if rules is not None else discover_rules()

    # -- Helpers to partition rules by category --

    @property
    def realtime_rules(self) -> list[ScoringRule]:
        return [r for r in self.rules if r.rule_category == "realtime"]

    @property
    def gfw_rules(self) -> list[ScoringRule]:
        return [r for r in self.rules if r.rule_category == "gfw_sourced"]

    # -- Core evaluation --

    async def evaluate_realtime(self, mmsi: int) -> list[RuleResult]:
        """Evaluate all real-time rules for *mmsi*.

        Loads the vessel profile, recent positions (last 48 h) and existing
        anomalies from the database.
        """
        session_factory = get_session()
        async with session_factory() as session:
            profile = await get_vessel_profile_by_mmsi(session, mmsi)
            now = datetime.now(timezone.utc)
            recent_positions = await get_vessel_track(
                session, mmsi, now - timedelta(hours=48), now
            )
            existing_anomalies = await list_anomaly_events_by_mmsi(session, mmsi)

            results: list[RuleResult] = []
            for rule in self.realtime_rules:
                try:
                    result = await rule.evaluate(
                        mmsi, profile, recent_positions, existing_anomalies, []
                    )
                except Exception:
                    logger.exception(
                        "Rule %s failed for MMSI %d", rule.rule_id, mmsi
                    )
                    continue
                if result is not None:
                    results.append(result)

            # Persist fired anomalies
            for result in results:
                if result.fired:
                    await self._create_anomaly(session, mmsi, result)

            await session.commit()

        return results

    async def evaluate_gfw(self, mmsi: int) -> list[RuleResult]:
        """Evaluate all GFW-sourced rules for *mmsi*.

        Loads the vessel profile, GFW events and existing anomalies from
        the database.
        """
        session_factory = get_session()
        async with session_factory() as session:
            profile = await get_vessel_profile_by_mmsi(session, mmsi)
            gfw_events = await list_gfw_events_by_mmsi(session, mmsi)
            existing_anomalies = await list_anomaly_events_by_mmsi(session, mmsi)

            results: list[RuleResult] = []
            for rule in self.gfw_rules:
                try:
                    result = await rule.evaluate(
                        mmsi, profile, [], existing_anomalies, gfw_events
                    )
                except Exception:
                    logger.exception(
                        "Rule %s failed for MMSI %d", rule.rule_id, mmsi
                    )
                    continue
                if result is not None:
                    results.append(result)

            # Persist fired anomalies
            for result in results:
                if result.fired:
                    await self._create_anomaly(session, mmsi, result)

            await session.commit()

        return results

    # -- Persistence helpers --

    @staticmethod
    async def _create_anomaly(
        session: Any, mmsi: int, result: RuleResult
    ) -> int:
        """Write a single anomaly_event row from a fired rule result."""
        data = {
            "mmsi": mmsi,
            "rule_id": result.rule_id,
            "severity": result.severity,
            "points": result.points,
            "details": json.dumps(result.details),
        }
        return await create_anomaly_event(session, data)
