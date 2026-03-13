"""Scoring engine: auto-discovers rules, evaluates them, persists anomalies.

The engine subscribes to two Redis pub/sub channels:

- ``heimdal:positions`` — triggers real-time rule evaluation
- ``heimdal:enrichment_complete`` — triggers GFW-sourced rule evaluation

After rule evaluation, the engine:
- Aggregates anomaly scores (with per-rule caps)
- Calculates risk tier (green/yellow/red)
- Updates the vessel profile in the database
- Publishes tier changes and new anomalies to Redis
- Deduplicates overlapping GFW and real-time anomalies
"""

from __future__ import annotations

import importlib
import inspect
import json
import logging
import pkgutil
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import text

from shared.db.connection import get_session
from shared.db.repositories import (
    count_ended_events,
    create_anomaly_event,
    end_anomaly_event,
    get_vessel_profile_by_mmsi,
    get_vessel_track,
    list_active_anomalies_by_mmsi,
    list_anomaly_events_by_mmsi,
    list_gfw_events_by_mmsi,
)
from shared.models.anomaly import RuleResult

from aggregator import (
    aggregate_score,
    calculate_tier,
    find_suppressed_anomalies,
    publish_anomaly,
    publish_risk_change,
)
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

    def __init__(
        self,
        rules: list[ScoringRule] | None = None,
        redis_client: Any | None = None,
    ) -> None:
        self.rules: list[ScoringRule] = rules if rules is not None else discover_rules()
        self.redis_client = redis_client

    # -- Helpers to partition rules by category --

    @property
    def realtime_rules(self) -> list[ScoringRule]:
        return [r for r in self.rules if r.rule_category == "realtime"]

    @property
    def gfw_rules(self) -> list[ScoringRule]:
        return [r for r in self.rules if r.rule_category == "gfw_sourced"]

    # -- Core evaluation --

    async def _check_and_end_active_events(
        self, session: Any, mmsi: int, profile: dict, recent_positions: list
    ) -> list[int]:
        """Check all active anomalies for this MMSI and end those whose conditions have ceased.
        Returns list of ended anomaly IDs."""
        active_anomalies = await list_active_anomalies_by_mmsi(session, mmsi)
        ended_ids: list[int] = []

        # Build a lookup of rules by rule_id
        rule_lookup = {r.rule_id: r for r in self.rules}

        for anomaly in active_anomalies:
            rule_id = anomaly.get("rule_id", "")
            rule = rule_lookup.get(rule_id)
            if rule is None:
                continue

            try:
                should_end = await rule.check_event_ended(
                    mmsi, profile, recent_positions, anomaly
                )
            except Exception:
                logger.exception("check_event_ended failed for rule %s, MMSI %d", rule_id, mmsi)
                continue

            if should_end:
                anomaly_id = anomaly.get("id")
                if anomaly_id is not None:
                    await end_anomaly_event(session, anomaly_id)
                    ended_ids.append(anomaly_id)
                    logger.info(
                        "Ended anomaly %d (rule=%s, mmsi=%d)",
                        anomaly_id, rule_id, mmsi,
                    )

        return ended_ids

    async def evaluate_realtime(self, mmsi: int) -> list[RuleResult]:
        """Evaluate all real-time rules for *mmsi*.

        Loads the vessel profile, recent positions (last 48 h) and existing
        anomalies from the database.  After persisting new anomalies,
        recalculates the aggregate score, updates the vessel profile, and
        publishes events to Redis.
        """
        eval_start = time.monotonic()
        session_factory = get_session()
        async with session_factory() as session:
            profile = await get_vessel_profile_by_mmsi(session, mmsi)
            if not profile:
                logger.debug("No vessel_profile for MMSI %d, skipping realtime eval", mmsi)
                return []
            now = datetime.now(timezone.utc)
            recent_positions = await get_vessel_track(
                session, mmsi, now - timedelta(hours=48), now
            )

            # Check and end active anomalies whose conditions have ceased
            ended_ids = await self._check_and_end_active_events(
                session, mmsi, profile, recent_positions
            )

            existing_anomalies = await list_anomaly_events_by_mmsi(session, mmsi)

            results: list[RuleResult] = []
            rules_fired = 0
            for rule in self.realtime_rules:
                rule_start = time.monotonic()
                try:
                    result = await rule.evaluate(
                        mmsi, profile, recent_positions, existing_anomalies, []
                    )
                except Exception:
                    rule_ms = (time.monotonic() - rule_start) * 1000
                    logger.exception(
                        "Rule %s failed for MMSI %d", rule.rule_id, mmsi,
                        extra={"rule_id": rule.rule_id, "mmsi": mmsi, "duration_ms": round(rule_ms, 2)},
                    )
                    continue
                rule_ms = (time.monotonic() - rule_start) * 1000
                if rule_ms > 100:
                    logger.warning(
                        "Slow rule evaluation",
                        extra={"slow_rule": True, "rule_id": rule.rule_id, "duration_ms": round(rule_ms, 2), "mmsi": mmsi},
                    )
                if result is not None:
                    results.append(result)
                    if result.fired:
                        rules_fired += 1

            total_ms = (time.monotonic() - eval_start) * 1000
            logger.info(
                "Vessel evaluation complete",
                extra={
                    "mmsi": mmsi,
                    "total_evaluation_ms": round(total_ms, 2),
                    "rules_evaluated": len(self.realtime_rules),
                    "rules_fired": rules_fired,
                },
            )

            # Persist fired anomalies — skip if an unresolved anomaly for the
            # same rule_id already exists (prevents duplicate rows on every
            # position update for static rules like identity_mismatch).
            existing_rule_ids = {
                a["rule_id"]
                for a in existing_anomalies
                if not a.get("resolved", False)
            }
            fired_results = [r for r in results if r.fired]
            new_results: list[RuleResult] = []
            for result in fired_results:
                if result.rule_id in existing_rule_ids:
                    continue  # already have an active anomaly for this rule
                new_results.append(result)
                await self._create_anomaly(session, mmsi, result)
                if self.redis_client is not None:
                    await publish_anomaly(
                        self.redis_client,
                        mmsi,
                        result.rule_id,
                        result.severity or "unknown",
                        result.points,
                        result.details,
                    )

            await session.commit()

            # Always recalculate score — enrichment may have added data that
            # changes existing anomaly evaluation even without new firings
            trigger_rule = new_results[0].rule_id if new_results else "realtime_rescore"
            await self._update_score_and_tier(
                session, mmsi, profile, trigger_rule
            )

        return results

    async def evaluate_gfw(self, mmsi: int) -> list[RuleResult]:
        """Evaluate all GFW-sourced rules for *mmsi*.

        Loads the vessel profile, GFW events and existing anomalies from
        the database.  After persisting new anomalies, runs dedup to
        suppress overlapping real-time anomalies, recalculates the
        aggregate score, updates the vessel profile, and publishes events.
        """
        eval_start = time.monotonic()
        session_factory = get_session()
        async with session_factory() as session:
            profile = await get_vessel_profile_by_mmsi(session, mmsi)
            if not profile:
                logger.debug("No vessel_profile for MMSI %d, skipping GFW eval", mmsi)
                return []
            gfw_events = await list_gfw_events_by_mmsi(session, mmsi)
            existing_anomalies = await list_anomaly_events_by_mmsi(session, mmsi)

            results: list[RuleResult] = []
            rules_fired = 0
            for rule in self.gfw_rules:
                rule_start = time.monotonic()
                try:
                    result = await rule.evaluate(
                        mmsi, profile, [], existing_anomalies, gfw_events
                    )
                except Exception:
                    rule_ms = (time.monotonic() - rule_start) * 1000
                    logger.exception(
                        "Rule %s failed for MMSI %d", rule.rule_id, mmsi,
                        extra={"rule_id": rule.rule_id, "mmsi": mmsi, "duration_ms": round(rule_ms, 2)},
                    )
                    continue
                rule_ms = (time.monotonic() - rule_start) * 1000
                if rule_ms > 100:
                    logger.warning(
                        "Slow rule evaluation",
                        extra={"slow_rule": True, "rule_id": rule.rule_id, "duration_ms": round(rule_ms, 2), "mmsi": mmsi},
                    )
                if result is not None:
                    results.append(result)
                    if result.fired:
                        rules_fired += 1

            total_ms = (time.monotonic() - eval_start) * 1000
            logger.info(
                "Vessel evaluation complete",
                extra={
                    "mmsi": mmsi,
                    "total_evaluation_ms": round(total_ms, 2),
                    "rules_evaluated": len(self.gfw_rules),
                    "rules_fired": rules_fired,
                },
            )

            # Persist fired anomalies, run dedup, publish anomaly events
            # Skip if an unresolved anomaly for the same rule already exists
            existing_rule_ids = {
                a["rule_id"]
                for a in existing_anomalies
                if not a.get("resolved", False)
            }
            fired_results = [r for r in results if r.fired]
            for result in fired_results:
                if result.rule_id in existing_rule_ids:
                    continue

                await self._create_anomaly(session, mmsi, result)

                # Dedup: suppress real-time anomalies that overlap
                gfw_time = datetime.now(timezone.utc)
                suppressed = find_suppressed_anomalies(
                    result.rule_id, gfw_time, existing_anomalies
                )
                for anomaly in suppressed:
                    anomaly_id = anomaly.get("id")
                    if anomaly_id is not None:
                        await self._resolve_anomaly(session, anomaly_id)

                if self.redis_client is not None:
                    await publish_anomaly(
                        self.redis_client,
                        mmsi,
                        result.rule_id,
                        result.severity or "unknown",
                        result.points,
                        result.details,
                    )

            await session.commit()

            # Always recalculate score after GFW evaluation
            trigger_rule = fired_results[0].rule_id if fired_results else "gfw_rescore"
            await self._update_score_and_tier(
                session, mmsi, profile, trigger_rule
            )

        return results

    # -- Score and tier update --

    async def _update_score_and_tier(
        self,
        session: Any,
        mmsi: int,
        profile: dict[str, Any] | None,
        trigger_rule: str,
    ) -> None:
        """Recalculate aggregate score, update the vessel profile, and
        publish a tier change event if the tier changed."""
        # Re-fetch anomalies to include newly persisted + deduped ones
        query_start = time.monotonic()
        all_anomalies = await list_anomaly_events_by_mmsi(session, mmsi)
        query_ms = (time.monotonic() - query_start) * 1000
        logger.debug(
            "Aggregate score query completed",
            extra={"mmsi": mmsi, "query_duration_ms": round(query_ms, 2), "anomaly_count": len(all_anomalies)},
        )
        new_score = aggregate_score(all_anomalies)
        new_tier = calculate_tier(new_score)

        old_tier = (profile or {}).get("risk_tier", "green") or "green"

        # Update vessel profile
        await session.execute(
            text(
                "UPDATE vessel_profiles "
                "SET risk_score = :score, risk_tier = :tier, updated_at = NOW() "
                "WHERE mmsi = :mmsi"
            ),
            {"score": new_score, "tier": new_tier, "mmsi": mmsi},
        )
        await session.commit()

        # Publish tier change only if tier actually changed
        if new_tier != old_tier and self.redis_client is not None:
            await publish_risk_change(
                self.redis_client, mmsi, old_tier, new_tier, new_score, trigger_rule
            )

    # -- Persistence helpers --

    # Default escalation multipliers: 1st occurrence, 2nd, 3rd+
    ESCALATION_MULTIPLIERS: list[float] = [1.0, 1.5, 2.0]
    ESCALATION_DECAY_DAYS: int = 30

    @staticmethod
    async def _create_anomaly(
        session: Any, mmsi: int, result: RuleResult
    ) -> int:
        """Write a single anomaly_event row from a fired rule result.

        Applies escalation multiplier based on how many ended events for the
        same (mmsi, rule_id) exist within the decay window.
        """
        # Count previous ended events for this (mmsi, rule_id) within decay window
        ended_count = await count_ended_events(
            session, mmsi, result.rule_id,
            decay_days=ScoringEngine.ESCALATION_DECAY_DAYS,
        )

        # Apply escalation multiplier
        multipliers = ScoringEngine.ESCALATION_MULTIPLIERS
        multiplier_idx = min(ended_count, len(multipliers) - 1)
        multiplier = multipliers[multiplier_idx]

        escalated_points = result.points * multiplier

        # Store escalation info in details
        details = dict(result.details) if result.details else {}
        if ended_count > 0:
            details["occurrence_number"] = ended_count + 1
            details["escalation_multiplier"] = multiplier

        data = {
            "mmsi": mmsi,
            "rule_id": result.rule_id,
            "severity": result.severity,
            "points": escalated_points,
            "details": json.dumps(details),
        }
        return await create_anomaly_event(session, data)

    @staticmethod
    async def _resolve_anomaly(session: Any, anomaly_id: int) -> None:
        """Mark an anomaly as resolved (used by dedup logic)."""
        await session.execute(
            text("UPDATE anomaly_events SET resolved = true WHERE id = :id"),
            {"id": anomaly_id},
        )
