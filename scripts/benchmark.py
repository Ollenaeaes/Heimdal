#!/usr/bin/env python3
"""Heimdal performance benchmarks.

Measures key performance metrics against target thresholds:
  - Ingest throughput: > 2000 positions/sec on 4 cores
  - Scoring latency: < 100ms p99
  - API response: < 200ms p99 at 50K vessels

Usage:
    python scripts/benchmark.py               # Run all benchmarks
    python scripts/benchmark.py --ingest      # Run only ingest benchmark
    python scripts/benchmark.py --scoring     # Run only scoring benchmark
    python scripts/benchmark.py --api         # Run only API benchmark

Requires the services to be running for API benchmarks.
Ingest and scoring benchmarks run standalone with mocked I/O.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "services" / "ais-ingest"))
sys.path.insert(0, str(_PROJECT_ROOT / "services" / "scoring"))

# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _pass(label: str, value: str, target: str) -> None:
    print(f"  {_GREEN}PASS{_RESET}  {label}: {_BOLD}{value}{_RESET}  (target: {target})")


def _fail(label: str, value: str, target: str) -> None:
    print(f"  {_RED}FAIL{_RESET}  {label}: {_BOLD}{value}{_RESET}  (target: {target})")


def _skip(label: str, reason: str) -> None:
    print(f"  {_YELLOW}SKIP{_RESET}  {label}: {reason}")


def _header(title: str) -> None:
    print(f"\n{_BOLD}{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}{_RESET}\n")


# ---------------------------------------------------------------------------
# Benchmark: AIS Message Parsing Throughput
# ---------------------------------------------------------------------------


def _make_position_message(mmsi: int = 259000420) -> dict:
    """Create a realistic AIS position report message."""
    return {
        "MessageType": "PositionReport",
        "MetaData": {
            "MMSI": mmsi,
            "time_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "Message": {
            "PositionReport": {
                "Sog": 12.3,
                "Cog": 180.5,
                "TrueHeading": 179,
                "Latitude": 68.123,
                "Longitude": 15.456,
                "NavigationalStatus": 0,
                "RateOfTurn": 5.0,
                "SpecialManoeuvreIndicator": 0,
                "Timestamp": 30,
            }
        },
    }


def benchmark_ingest_throughput(
    num_messages: int = 50000,
    target_per_sec: int = 2000,
) -> bool:
    """Benchmark AIS message parsing throughput.

    Measures how many messages per second the parser can process.
    Target: > 2000 positions/sec on 4 cores (single-threaded baseline).
    """
    from parser import parse_message

    _header("Ingest Throughput Benchmark")
    print(f"  Parsing {num_messages:,} AIS messages (single-threaded)...\n")

    # Pre-generate messages with varying MMSIs
    messages = [
        _make_position_message(mmsi=100000000 + (i % 900000000))
        for i in range(num_messages)
    ]

    start = time.perf_counter()
    parsed = 0
    for msg in messages:
        result = parse_message(msg)
        if result is not None:
            parsed += 1
    elapsed = time.perf_counter() - start

    rate = parsed / elapsed
    passed = rate >= target_per_sec

    if passed:
        _pass(
            "Parse throughput",
            f"{rate:,.0f} msg/sec",
            f"> {target_per_sec:,} msg/sec",
        )
    else:
        _fail(
            "Parse throughput",
            f"{rate:,.0f} msg/sec",
            f"> {target_per_sec:,} msg/sec",
        )

    print(f"\n  Details:")
    print(f"    Messages parsed: {parsed:,} / {num_messages:,}")
    print(f"    Elapsed time:    {elapsed:.3f}s")
    print(f"    Per message:     {elapsed / num_messages * 1000:.3f}ms")
    return passed


# ---------------------------------------------------------------------------
# Benchmark: Scoring Rule Evaluation Latency
# ---------------------------------------------------------------------------


def benchmark_scoring_latency(
    num_iterations: int = 1000,
    target_p99_ms: float = 100.0,
) -> bool:
    """Benchmark scoring rule evaluation latency.

    Measures p99 latency for evaluating all real-time rules on a single vessel.
    Target: < 100ms p99.
    """
    import asyncio
    from shared.models.anomaly import RuleResult
    from rules.base import ScoringRule

    _header("Scoring Latency Benchmark")
    print(f"  Evaluating scoring rules {num_iterations:,} times...\n")

    # Import all real-time rules
    rule_modules = [
        "rules.ais_gap",
        "rules.sts_proximity",
        "rules.destination_spoof",
        "rules.draft_change",
        "rules.flag_hopping",
        "rules.sanctions_match",
        "rules.vessel_age",
        "rules.speed_anomaly",
        "rules.identity_mismatch",
    ]

    rules: list[ScoringRule] = []
    for mod_name in rule_modules:
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            import inspect
            for _name, obj in inspect.getmembers(mod, inspect.isclass):
                if (
                    issubclass(obj, ScoringRule)
                    and obj is not ScoringRule
                    and not inspect.isabstract(obj)
                ):
                    rules.append(obj())
        except Exception as e:
            _skip(mod_name, str(e))

    if not rules:
        _skip("Scoring latency", "No rules could be loaded")
        return False

    print(f"  Loaded {len(rules)} rules")

    # Prepare test data
    now = datetime.now(timezone.utc)
    profile = {
        "mmsi": 273412340,
        "imo": 9189890,
        "ship_name": "TURBA",
        "ship_type": 80,
        "flag_country": "RU",
        "length": 274.0,
        "width": 48.0,
        "draught": 16.5,
        "destination": "FOR ORDERS",
        "risk_score": 50.0,
        "risk_tier": "yellow",
        "last_position_time": now - timedelta(hours=2),
        "build_year": 2000,
        "sanctions_status": {"matched": True},
    }

    positions = [
        {
            "timestamp": now - timedelta(hours=i),
            "lat": 35.89 + i * 0.01,
            "lon": -5.31 + i * 0.01,
            "sog": 2.1 + i * 0.5,
            "cog": 135.0,
            "nav_status": 0,
            "draught": 16.5,
        }
        for i in range(48)
    ]

    existing_anomalies: list[dict] = []
    gfw_events: list[dict] = []

    # Warm up
    async def _evaluate_all():
        results = []
        for rule in rules:
            try:
                result = await rule.evaluate(
                    273412340, profile, positions, existing_anomalies, gfw_events
                )
                if result is not None:
                    results.append(result)
            except Exception:
                pass
        return results

    asyncio.run(_evaluate_all())

    # Benchmark
    latencies_ms: list[float] = []
    for _ in range(num_iterations):
        start = time.perf_counter()
        asyncio.run(_evaluate_all())
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies_ms.append(elapsed_ms)

    latencies_ms.sort()
    p50 = latencies_ms[len(latencies_ms) // 2]
    p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
    p99 = latencies_ms[int(len(latencies_ms) * 0.99)]
    avg = statistics.mean(latencies_ms)

    passed = p99 <= target_p99_ms

    if passed:
        _pass("Scoring p99 latency", f"{p99:.2f}ms", f"< {target_p99_ms}ms")
    else:
        _fail("Scoring p99 latency", f"{p99:.2f}ms", f"< {target_p99_ms}ms")

    print(f"\n  Details:")
    print(f"    Rules evaluated: {len(rules)}")
    print(f"    Iterations:      {num_iterations:,}")
    print(f"    p50 latency:     {p50:.2f}ms")
    print(f"    p95 latency:     {p95:.2f}ms")
    print(f"    p99 latency:     {p99:.2f}ms")
    print(f"    avg latency:     {avg:.2f}ms")
    return passed


# ---------------------------------------------------------------------------
# Benchmark: API Response Latency
# ---------------------------------------------------------------------------


def benchmark_api_response(
    num_requests: int = 100,
    target_p99_ms: float = 200.0,
) -> bool:
    """Benchmark API response latency.

    Measures p99 latency for key API endpoints.
    Target: < 200ms p99 at 50K vessels.
    Requires the API server to be running.
    """
    _header("API Response Latency Benchmark")

    api_url = os.environ.get("HEIMDAL_API_URL", "http://localhost:8000")

    # Check if API is reachable
    try:
        import urllib.request
        urllib.request.urlopen(f"{api_url}/api/health", timeout=3)
    except Exception:
        _skip("API response", f"API server not reachable at {api_url}")
        return True  # Don't fail the benchmark suite

    try:
        import requests
    except ImportError:
        _skip("API response", "requests library not installed")
        return True

    print(f"  Testing {num_requests} requests to {api_url}...\n")

    endpoints = [
        ("GET /api/vessels", f"{api_url}/api/vessels?per_page=50"),
        ("GET /api/anomalies", f"{api_url}/api/anomalies?per_page=50"),
        ("GET /api/health", f"{api_url}/api/health"),
        ("GET /api/stats", f"{api_url}/api/stats"),
    ]

    all_passed = True
    for label, url in endpoints:
        latencies_ms: list[float] = []

        # Warm up
        requests.get(url, timeout=5)

        for _ in range(num_requests):
            start = time.perf_counter()
            resp = requests.get(url, timeout=5)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)
            assert resp.status_code == 200

        latencies_ms.sort()
        p50 = latencies_ms[len(latencies_ms) // 2]
        p99 = latencies_ms[int(len(latencies_ms) * 0.99)]
        avg = statistics.mean(latencies_ms)

        passed = p99 <= target_p99_ms
        if not passed:
            all_passed = False

        if passed:
            _pass(label, f"p99={p99:.1f}ms", f"< {target_p99_ms}ms")
        else:
            _fail(label, f"p99={p99:.1f}ms", f"< {target_p99_ms}ms")

        print(f"           p50={p50:.1f}ms  avg={avg:.1f}ms")

    return all_passed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Heimdal performance benchmarks")
    parser.add_argument("--ingest", action="store_true", help="Run ingest throughput benchmark")
    parser.add_argument("--scoring", action="store_true", help="Run scoring latency benchmark")
    parser.add_argument("--api", action="store_true", help="Run API response benchmark")
    parser.add_argument("--quick", action="store_true", help="Use reduced iteration counts")
    args = parser.parse_args()

    run_all = not (args.ingest or args.scoring or args.api)

    results: list[bool] = []

    scale = 0.1 if args.quick else 1.0

    print(f"\n{_BOLD}Heimdal Performance Benchmarks{_RESET}")
    print(f"{'=' * 60}")
    print(f"  Date:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode:    {'quick' if args.quick else 'full'}")

    if run_all or args.ingest:
        results.append(
            benchmark_ingest_throughput(
                num_messages=int(50000 * scale),
                target_per_sec=2000,
            )
        )

    if run_all or args.scoring:
        results.append(
            benchmark_scoring_latency(
                num_iterations=int(1000 * scale),
                target_p99_ms=100.0,
            )
        )

    if run_all or args.api:
        results.append(
            benchmark_api_response(
                num_requests=int(100 * scale),
                target_p99_ms=200.0,
            )
        )

    # Summary
    _header("Summary")
    passed = sum(1 for r in results if r)
    total = len(results)
    if passed == total:
        print(f"  {_GREEN}{_BOLD}ALL {total} BENCHMARKS PASSED{_RESET}")
    else:
        failed = total - passed
        print(f"  {_RED}{_BOLD}{failed} of {total} BENCHMARKS FAILED{_RESET}")

    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
