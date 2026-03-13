"""Profile memory usage of key components.

Measures memory consumption of:
1. Scoring engine state for 10,000 simulated vessels
2. AIS ingest batch buffer (500 positions)
3. Frontend vessel store estimate (10,000 vessels)

Usage: python3 scripts/profile_memory.py
"""
import sys
import os
import tracemalloc
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'scoring'))


def profile_scoring_memory():
    """Profile scoring engine memory with simulated vessel data."""
    tracemalloc.start()

    from services.scoring.aggregator import aggregate_score

    # Simulated anomaly data per vessel — 14 rule IDs matching actual rule set
    rule_ids = [
        "ais_gap", "sts_proximity", "speed_anomaly", "sanctions_match",
        "gfw_ais_disabling", "gfw_encounter", "destination_spoof",
        "draft_change", "flag_hopping", "vessel_age", "identity_mismatch",
        "ais_spoofing", "ownership_risk", "insurance_class_risk",
    ]

    vessel_anomalies = {}
    for mmsi in range(200000000, 200010000):  # 10,000 vessels
        anomalies = []
        for i in range(3):  # avg 3 anomalies per vessel
            anomalies.append({
                "rule_id": rule_ids[i % len(rule_ids)],
                "points": 15.0,
                "resolved": False,
                "event_state": "active",
                "details": json.dumps({"occurrence_number": 1}),
            })
        vessel_anomalies[mmsi] = anomalies

    current, peak = tracemalloc.get_traced_memory()
    print(f"Scoring state for 10,000 vessels:")
    print(f"  Current: {current / 1024 / 1024:.1f} MB")
    print(f"  Peak:    {peak / 1024 / 1024:.1f} MB")

    # Run aggregation for all vessels to measure peak during processing
    for mmsi, anomalies in vessel_anomalies.items():
        aggregate_score(anomalies)

    current, peak = tracemalloc.get_traced_memory()
    print(f"After aggregation for all 10,000:")
    print(f"  Current: {current / 1024 / 1024:.1f} MB")
    print(f"  Peak:    {peak / 1024 / 1024:.1f} MB")

    tracemalloc.stop()
    return peak / 1024 / 1024


def profile_ingest_buffer():
    """Profile AIS ingest batch buffer memory."""
    tracemalloc.start()

    # Simulate 500 position messages in buffer (matches batch writer config)
    buffer = []
    for i in range(500):
        buffer.append({
            "timestamp": "2026-03-13T12:00:00+00:00",
            "mmsi": 200000000 + i,
            "lat": 60.0 + i * 0.001,
            "lon": 10.0 + i * 0.001,
            "sog": 12.5,
            "cog": 180.0,
            "heading": 180,
            "nav_status": 0,
            "rot": 0.0,
            "draught": 5.0,
        })

    current, peak = tracemalloc.get_traced_memory()
    print(f"\nIngest buffer (500 positions):")
    print(f"  Current: {current / 1024 / 1024:.1f} MB")
    print(f"  Peak:    {peak / 1024 / 1024:.1f} MB")

    tracemalloc.stop()
    return peak / 1024 / 1024


def profile_vessel_store():
    """Estimate frontend vessel store memory for 10,000 vessels.

    Cannot profile actual React store from Python, but estimates based on
    equivalent data structure size. Each vessel entry mirrors the VesselState
    TypeScript interface.
    """
    tracemalloc.start()

    vessel_data = {}
    for i in range(10000):
        vessel_data[200000000 + i] = {
            "mmsi": 200000000 + i,
            "lat": 60.0 + i * 0.001,
            "lon": 10.0 + i * 0.001,
            "sog": 12.5,
            "cog": 180.0,
            "heading": 180,
            "risk_tier": "green",
            "ship_name": f"VESSEL {i}",
        }

    current, peak = tracemalloc.get_traced_memory()
    print(f"\nFrontend vessel store (10,000 vessels):")
    print(f"  Current: {current / 1024 / 1024:.1f} MB")
    print(f"  Peak:    {peak / 1024 / 1024:.1f} MB")

    # Also compute a per-entry estimate for documentation
    estimated_per_entry_bytes = 500  # ~500 bytes per vessel including strings
    estimated_mb = len(vessel_data) * estimated_per_entry_bytes / 1024 / 1024
    print(f"  Estimate (~500 bytes/vessel): {estimated_mb:.1f} MB")

    tracemalloc.stop()
    return peak / 1024 / 1024


def main():
    print("=" * 60)
    print("MEMORY PROFILING")
    print("=" * 60)

    scoring_mb = profile_scoring_memory()
    ingest_mb = profile_ingest_buffer()
    store_mb = profile_vessel_store()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Scoring engine (10K vessels): {scoring_mb:.1f} MB (target: <200 MB)")
    print(f"Ingest buffer (500 positions): {ingest_mb:.1f} MB (target: <10 MB)")
    print(f"Frontend store (10K vessels): {store_mb:.1f} MB (target: <100 MB)")

    # Check targets
    assert scoring_mb < 200, f"Scoring memory {scoring_mb:.1f} MB exceeds 200 MB target"
    assert ingest_mb < 10, f"Ingest buffer {ingest_mb:.1f} MB exceeds 10 MB target"
    assert store_mb < 100, f"Frontend store {store_mb:.1f} MB exceeds 100 MB target"

    print("\nAll memory targets met!")


if __name__ == "__main__":
    main()
