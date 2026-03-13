"""Profile the AIS ingest pipeline.

Profiles two key operations:
1. AIS message parsing (parse_position_report) with realistic messages
2. JSON serialization/deserialization throughput

Usage: python3 scripts/profile_ingest.py
"""
import cProfile
import pstats
import io
import json
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'ais-ingest'))


def generate_ais_messages(count=10000):
    """Generate realistic AIS position report messages."""
    messages = []
    base_time = datetime.now(timezone.utc)
    for i in range(count):
        msg = {
            "MessageType": "PositionReport",
            "MetaData": {
                "MMSI": 200000000 + (i % 1000),
                "time_utc": base_time.isoformat(),
            },
            "Message": {
                "PositionReport": {
                    "Latitude": 60.0 + (i % 100) * 0.01,
                    "Longitude": 10.0 + (i % 100) * 0.01,
                    "Sog": 12.5,
                    "Cog": 180.0,
                    "TrueHeading": 180,
                    "RateOfTurn": 0.0,
                    "NavigationalStatus": 0,
                }
            },
        }
        messages.append(msg)
    return messages


def profile_parsing(messages):
    """Profile message parsing."""
    from parser import parse_position_report

    for msg in messages:
        parse_position_report(msg)


def profile_json_parsing(messages):
    """Profile JSON serialization/deserialization."""
    json_strings = [json.dumps(m) for m in messages]

    for s in json_strings:
        json.loads(s)


def main():
    print("=" * 60)
    print("AIS INGEST PROFILING")
    print("=" * 60)

    messages = generate_ais_messages(10000)

    print(f"\n--- Parse {len(messages)} AIS messages ---")
    profiler = cProfile.Profile()
    profiler.enable()
    profile_parsing(messages)
    profiler.disable()

    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats('cumulative')
    stats.print_stats(20)
    print(stream.getvalue())

    print(f"\n--- JSON loads {len(messages)} messages ---")
    profiler2 = cProfile.Profile()
    profiler2.enable()
    profile_json_parsing(messages)
    profiler2.disable()

    stream2 = io.StringIO()
    stats2 = pstats.Stats(profiler2, stream=stream2)
    stats2.sort_stats('cumulative')
    stats2.print_stats(20)
    print(stream2.getvalue())


if __name__ == "__main__":
    main()
