#!/usr/bin/env python3
"""Rescore vessels affected by bulk-resolving false positive spoofing/speed anomalies.

Run AFTER applying migration 019_bulk_resolve_spoof_anomalies.sql.

Usage:
    python scripts/rescore_after_bulk_resolve.py --db-url postgresql://heimdal:heimdal@localhost:5432/heimdal
    python scripts/rescore_after_bulk_resolve.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

import psycopg2
import psycopg2.extras

# ---------------------------------------------------------------------------
# Inline copies of scoring constants so this script is self-contained
# (no dependency on the async app or its config loading).
# ---------------------------------------------------------------------------

MAX_PER_RULE: dict[str, int] = {
    "gfw_ais_disabling": 100,
    "gfw_encounter": 100,
    "gfw_loitering": 40,
    "gfw_port_visit": 40,
    "gfw_dark_sar": 40,
    "ais_gap": 20,
    "sts_proximity": 15,
    "destination_spoof": 15,
    "draft_change": 40,
    "flag_hopping": 40,
    "sanctions_match": 100,
    "vessel_age": 10,
    "speed_anomaly": 10,
    "identity_mismatch": 100,
    "flag_of_convenience": 10,
    "ais_spoofing": 0,
    "ownership_risk": 60,
    "insurance_class_risk": 60,
    "iacs_class_status": 60,
    "spoof_land_position": 0,
    "spoof_impossible_speed": 0,
    "spoof_duplicate_mmsi": 0,
    "spoof_frozen_position": 0,
    "spoof_identity_mismatch": 0,
    "voyage_pattern": 80,
    "cable_slow_transit": 140,
    "cable_alignment": 100,
    "infra_speed_anomaly": 15,
}

YELLOW_THRESHOLD = 30.0
RED_THRESHOLD = 80.0

_SANCTIONS_PROGRAMS = frozenset({
    "sanctions", "ua_war_sanctions", "eu_sanctions_map",
    "eu_journal_sanctions", "gb_fcdo_sanctions",
    "ca_dfatd_sema_sanctions", "ch_seco_sanctions",
    "us_sam_exclusions", "kp_rusi_reports",
    "us_ofac_sdn", "eu_fsf", "gb_hmt_sanctions", "un_sc_sanctions",
})

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scoring helpers (mirrors aggregator.py logic, sync/psycopg2 friendly)
# ---------------------------------------------------------------------------

def aggregate_score(anomalies: list[dict]) -> float:
    """Sum points from unresolved active anomalies with per-rule caps."""
    per_rule_totals: dict[str, float] = {}
    max_escalation: dict[str, float] = {}

    for a in anomalies:
        if a.get("resolved", False):
            continue
        state = a.get("event_state")
        if state is not None and state != "active":
            continue

        rule_id = a.get("rule_id", "")
        points = float(a.get("points", 0))
        per_rule_totals[rule_id] = per_rule_totals.get(rule_id, 0.0) + points

        details = a.get("details") or {}
        if isinstance(details, str):
            details = json.loads(details)
        mult = details.get("escalation_multiplier", 1.0) if isinstance(details, dict) else 1.0
        max_escalation[rule_id] = max(max_escalation.get(rule_id, 1.0), mult)

    total = 0.0
    for rule_id, raw in per_rule_totals.items():
        base_cap = MAX_PER_RULE.get(rule_id, raw)
        adj_cap = base_cap * max_escalation.get(rule_id, 1.0)
        total += min(raw, adj_cap)

    return total


def calculate_tier(score: float, anomalies: list[dict]) -> str:
    """Derive risk tier from score, checking for sanctions blacklist."""
    for a in anomalies:
        if a.get("resolved", False):
            continue
        if a.get("rule_id") != "sanctions_match":
            continue
        details = a.get("details") or {}
        if isinstance(details, str):
            details = json.loads(details)
        if not isinstance(details, dict):
            continue
        matched_field = details.get("matched_field", "")
        confidence = float(details.get("confidence", 0))
        program = details.get("program", "")
        if matched_field in ("imo", "mmsi") and confidence >= 0.9 and program in _SANCTIONS_PROGRAMS:
            return "blacklisted"

    if score >= RED_THRESHOLD:
        return "red"
    if score >= YELLOW_THRESHOLD:
        return "yellow"
    return "green"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Rescore vessels after bulk-resolving spoof/speed anomalies.")
    parser.add_argument(
        "--db-url",
        default="postgresql://heimdal:heimdal_dev@localhost:5432/heimdal",
        help="PostgreSQL connection string",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate new scores but don't write to DB",
    )
    args = parser.parse_args()

    conn = psycopg2.connect(args.db_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # 1. Find affected MMSIs (vessels that had anomalies bulk-resolved)
    cur.execute("""
        SELECT DISTINCT mmsi
        FROM anomaly_events
        WHERE details->>'resolution' LIKE 'bulk_resolved:%'
    """)
    affected_mmsis = [row["mmsi"] for row in cur.fetchall()]
    logger.info("Found %d affected vessels with bulk-resolved anomalies.", len(affected_mmsis))

    if not affected_mmsis:
        logger.info("Nothing to rescore. Done.")
        cur.close()
        conn.close()
        return

    # Count how many anomalies were resolved (for summary)
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM anomaly_events
        WHERE details->>'resolution' LIKE 'bulk_resolved:%'
    """)
    resolved_count = cur.fetchone()["cnt"]

    # 2. For each MMSI, get ALL anomalies and rescore
    tier_changes: list[dict] = []
    rescored_count = 0

    for mmsi in affected_mmsis:
        # Get all anomalies for this vessel
        cur.execute("""
            SELECT rule_id, severity, points, details, resolved, event_state
            FROM anomaly_events
            WHERE mmsi = %s
        """, (mmsi,))
        anomalies = [dict(row) for row in cur.fetchall()]

        new_score = aggregate_score(anomalies)
        new_tier = calculate_tier(new_score, anomalies)

        # Get current score/tier
        cur.execute("""
            SELECT risk_score, risk_tier
            FROM vessel_profiles
            WHERE mmsi = %s
        """, (mmsi,))
        row = cur.fetchone()
        if row is None:
            # No vessel profile — skip
            continue

        old_score = float(row["risk_score"]) if row["risk_score"] is not None else 0.0
        old_tier = row["risk_tier"] or "green"

        if not args.dry_run:
            cur.execute("""
                UPDATE vessel_profiles
                SET risk_score = %s, risk_tier = %s
                WHERE mmsi = %s
            """, (new_score, new_tier, mmsi))

        rescored_count += 1

        if old_tier != new_tier:
            tier_changes.append({
                "mmsi": mmsi,
                "old_tier": old_tier,
                "new_tier": new_tier,
                "old_score": old_score,
                "new_score": new_score,
            })

    if not args.dry_run:
        conn.commit()
        logger.info("Changes committed.")
    else:
        conn.rollback()
        logger.info("DRY RUN — no changes written.")

    # 3. Summary
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info("Anomalies resolved:     %d", resolved_count)
    logger.info("Vessels rescored:       %d", rescored_count)
    logger.info("Tier changes:           %d", len(tier_changes))

    if tier_changes:
        logger.info("")
        logger.info("Tier change details:")
        for tc in tier_changes:
            logger.info(
                "  MMSI %s: %s (%.1f) -> %s (%.1f)",
                tc["mmsi"], tc["old_tier"], tc["old_score"],
                tc["new_tier"], tc["new_score"],
            )

        # Breakdown by transition type
        transitions: dict[str, int] = {}
        for tc in tier_changes:
            key = f"{tc['old_tier']} -> {tc['new_tier']}"
            transitions[key] = transitions.get(key, 0) + 1
        logger.info("")
        logger.info("Tier transition breakdown:")
        for transition, count in sorted(transitions.items()):
            logger.info("  %s: %d vessels", transition, count)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
