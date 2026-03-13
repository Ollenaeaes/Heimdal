"""Profile the scoring engine under realistic load.

Profiles two key operations:
1. Score aggregation (aggregate_score) with realistic anomaly data
2. Rule discovery (discover_rules) import overhead

Usage: python3 scripts/profile_scoring.py
"""
import asyncio
import cProfile
import pstats
import io
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'scoring'))


def profile_aggregation():
    """Profile the aggregate_score function with realistic data."""
    from services.scoring.aggregator import aggregate_score

    # Create realistic anomaly data — 500 anomalies across vessels
    rule_ids = [
        "ais_gap", "sts_proximity", "speed_anomaly", "sanctions_match",
        "gfw_ais_disabling", "gfw_encounter", "destination_spoof",
        "draft_change", "flag_hopping", "vessel_age", "identity_mismatch",
        "ais_spoofing", "ownership_risk", "insurance_class_risk",
    ]

    anomalies = []
    for i in range(500):
        anomalies.append({
            "rule_id": rule_ids[i % len(rule_ids)],
            "points": 15.0 + (i % 20),
            "resolved": False,
            "event_state": "active",
            "details": '{"occurrence_number": 1}',
        })

    # Profile aggregation over 10,000 iterations
    for _ in range(10000):
        aggregate_score(anomalies)


def profile_rule_evaluation():
    """Profile rule imports and discovery."""
    from services.scoring.engine import discover_rules

    rules = discover_rules()
    print(f"Discovered {len(rules)} rules")

    # Profile just the rule creation overhead
    for _ in range(100):
        discover_rules()


def main():
    print("=" * 60)
    print("SCORING ENGINE PROFILING")
    print("=" * 60)

    # Profile aggregation
    print("\n--- aggregate_score (10,000 iterations, 500 anomalies) ---")
    profiler = cProfile.Profile()
    profiler.enable()
    profile_aggregation()
    profiler.disable()

    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats('cumulative')
    stats.print_stats(20)
    print(stream.getvalue())

    # Profile rule discovery
    print("\n--- Rule Discovery (100 iterations) ---")
    profiler2 = cProfile.Profile()
    profiler2.enable()
    profile_rule_evaluation()
    profiler2.disable()

    stream2 = io.StringIO()
    stats2 = pstats.Stats(profiler2, stream=stream2)
    stats2.sort_stats('cumulative')
    stats2.print_stats(20)
    print(stream2.getvalue())


if __name__ == "__main__":
    main()
