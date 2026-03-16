"""Score aggregation, tier calculation, and GFW/real-time dedup logic.

This module provides three capabilities:

1. **Score aggregation** — sum unresolved anomaly points with per-rule caps.
2. **Tier calculation** — map aggregate score to green/yellow/red, or blacklisted for confirmed sanctions.
3. **Dedup** — when a GFW-sourced anomaly overlaps a real-time anomaly for
   the same vessel and time window, suppress (resolve) the real-time anomaly.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from shared.config import settings
from shared.constants import MAX_PER_RULE

logger = logging.getLogger("scoring.aggregator")

# ---------------------------------------------------------------------------
# Dedup mapping: GFW rule_id → real-time rule_id it suppresses
# ---------------------------------------------------------------------------
GFW_DEDUP_PAIRS: dict[str, str] = {
    "gfw_ais_disabling": "ais_gap",
    "gfw_encounter": "sts_proximity",
    "gfw_loitering": "sts_proximity",
    # gfw_port_visit has no real-time equivalent
}

# Dedup window: GFW event overlaps real-time anomaly ±6 hours
DEDUP_WINDOW_HOURS: int = 6


# ---------------------------------------------------------------------------
# Tier calculation
# ---------------------------------------------------------------------------


def calculate_tier(
    score: float,
    anomalies: Sequence[dict[str, Any]] | None = None,
) -> str:
    """Return risk tier for a given score.

    Uses thresholds from ``settings.scoring``.

    If *anomalies* are provided and the vessel has an active
    ``sanctions_match`` anomaly with ``matched_field`` in ('imo', 'mmsi')
    and confidence >= 0.9, returns ``'blacklisted'`` regardless of score.
    """
    # Check for confirmed sanctions match → blacklisted (not score-based).
    # Only actual sanctions programs qualify — MoU detentions, PSC records,
    # and other non-sanctions datasets are informational, not blacklist-worthy.
    _SANCTIONS_PROGRAMS = frozenset({
        "sanctions", "ua_war_sanctions", "eu_sanctions_map",
        "eu_journal_sanctions", "gb_fcdo_sanctions",
        "ca_dfatd_sema_sanctions", "ch_seco_sanctions",
        "us_sam_exclusions", "kp_rusi_reports",
        "us_ofac_sdn", "eu_fsf", "gb_hmt_sanctions", "un_sc_sanctions",
    })
    if anomalies:
        for anomaly in anomalies:
            if anomaly.get("resolved", False):
                continue
            if anomaly.get("rule_id") != "sanctions_match":
                continue
            details = anomaly.get("details", {})
            if isinstance(details, str):
                details = json.loads(details)
            if not isinstance(details, dict):
                continue
            matched_field = details.get("matched_field", "")
            confidence = float(details.get("confidence", 0))
            program = details.get("program", "")
            if matched_field in ("imo", "mmsi") and confidence >= 0.9 and program in _SANCTIONS_PROGRAMS:
                return "blacklisted"

    if score >= settings.scoring.red_threshold:
        return "red"
    if score >= settings.scoring.yellow_threshold:
        return "yellow"
    return "green"


# ---------------------------------------------------------------------------
# Score aggregation
# ---------------------------------------------------------------------------


def aggregate_score(anomalies: Sequence[dict[str, Any]]) -> float:
    """Sum points from unresolved, active anomalies, capping each rule at its
    ``MAX_PER_RULE`` value (adjusted by escalation multiplier when present).

    Only unresolved anomalies with ``event_state`` of ``'active'`` (or
    ``None`` for backward compatibility) contribute.  Each rule_id's total
    is capped at ``MAX_PER_RULE[rule_id]``, scaled by the highest escalation
    multiplier found among that rule's anomalies.
    """
    per_rule_totals: dict[str, float] = {}
    max_escalation_per_rule: dict[str, float] = {}

    for anomaly in anomalies:
        if anomaly.get("resolved", False):
            continue
        # Only count active anomalies (backward compat: treat None/missing as active)
        event_state = anomaly.get("event_state")
        if event_state is not None and event_state != "active":
            continue
        rule_id = anomaly.get("rule_id", "")
        points = float(anomaly.get("points", 0))
        per_rule_totals[rule_id] = per_rule_totals.get(rule_id, 0.0) + points

        # Track highest escalation multiplier for cap adjustment
        details = anomaly.get("details", {})
        if isinstance(details, str):
            details = json.loads(details)
        mult = details.get("escalation_multiplier", 1.0) if isinstance(details, dict) else 1.0
        max_escalation_per_rule[rule_id] = max(
            max_escalation_per_rule.get(rule_id, 1.0), mult
        )

    total = 0.0
    for rule_id, raw_total in per_rule_totals.items():
        base_cap = MAX_PER_RULE.get(rule_id, raw_total)  # fallback: no cap
        escalation = max_escalation_per_rule.get(rule_id, 1.0)
        adjusted_cap = base_cap * escalation
        total += min(raw_total, adjusted_cap)

    return total


# ---------------------------------------------------------------------------
# Dedup logic
# ---------------------------------------------------------------------------


def find_suppressed_anomalies(
    gfw_rule_id: str,
    gfw_created_at: datetime,
    existing_anomalies: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return real-time anomalies that should be suppressed (resolved) by
    the given GFW rule firing.

    A real-time anomaly is suppressed when:
    - Its ``rule_id`` is the dedup partner for *gfw_rule_id*
    - It is not already resolved
    - Its ``created_at`` falls within ±DEDUP_WINDOW_HOURS of *gfw_created_at*
    """
    rt_rule_id = GFW_DEDUP_PAIRS.get(gfw_rule_id)
    if rt_rule_id is None:
        return []

    window_start = gfw_created_at - timedelta(hours=DEDUP_WINDOW_HOURS)
    window_end = gfw_created_at + timedelta(hours=DEDUP_WINDOW_HOURS)

    suppressed: list[dict[str, Any]] = []
    for anomaly in existing_anomalies:
        if anomaly.get("resolved", False):
            continue
        if anomaly.get("rule_id") != rt_rule_id:
            continue

        anomaly_time = anomaly.get("created_at")
        if anomaly_time is None:
            continue

        # Ensure timezone-aware comparison
        if isinstance(anomaly_time, datetime):
            if anomaly_time.tzinfo is None:
                anomaly_time = anomaly_time.replace(tzinfo=timezone.utc)
            if window_start <= anomaly_time <= window_end:
                suppressed.append(anomaly)

    return suppressed


# ---------------------------------------------------------------------------
# Redis publishing helpers
# ---------------------------------------------------------------------------


async def publish_risk_change(
    redis_client: Any,
    mmsi: int,
    old_tier: str,
    new_tier: str,
    score: float,
    trigger_rule: str,
) -> None:
    """Publish a tier change event to ``heimdal:risk_changes``."""
    payload = {
        "mmsi": mmsi,
        "old_tier": old_tier,
        "new_tier": new_tier,
        "score": score,
        "trigger_rule": trigger_rule,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await redis_client.publish("heimdal:risk_changes", json.dumps(payload))
    logger.info(
        "Risk change published: MMSI %d %s → %s (score=%.1f, trigger=%s)",
        mmsi, old_tier, new_tier, score, trigger_rule,
    )


async def publish_anomaly(
    redis_client: Any,
    mmsi: int,
    rule_id: str,
    severity: str,
    points: float,
    details: dict,
) -> None:
    """Publish a new anomaly event to ``heimdal:anomalies``."""
    payload = {
        "mmsi": mmsi,
        "rule_id": rule_id,
        "severity": severity,
        "points": points,
        "details": details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await redis_client.publish("heimdal:anomalies", json.dumps(payload))
