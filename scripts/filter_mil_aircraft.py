#!/usr/bin/env python3
"""
Filter basic-ac-db.json for Nordic military, government, and NATO patrol aircraft.

Step 1: Nordic military (mil=True + Nordic ICAO hex ranges)
Step 2: Nordic government operators (coast guard, police, border guard)
Step 3: US/NATO patrol aircraft relevant to Baltic/Nordic operations
"""

import json
import re
import sys
from pathlib import Path

INPUT = Path(__file__).parent.parent / "data" / "adsb" / "basic-ac-db.json"
OUTPUT = Path(__file__).parent.parent / "data" / "adsb" / "nordic_mil_gov.json"

# --- ICAO hex ranges ---

NORDIC_RANGES = [
    (0x478000, 0x47FFFF, "Norway"),
    (0x4A8000, 0x4AFFFF, "Sweden"),
    (0x458000, 0x45FFFF, "Denmark"),
    (0x460000, 0x467FFF, "Finland"),
]

NATO_MIL_RANGES = [
    (0xAE0000, 0xAFFFFF, "USA military"),
    (0x400000, 0x43FFFF, "UK military"),
    (0x3C0000, 0x3FFFFF, "Germany"),
]

# Types relevant for NATO maritime patrol / ISR over Baltic/Nordic
NATO_PATROL_TYPES = {
    "P8", "P8A",       # P-8A Poseidon
    "RC35",             # RC-135 Rivet Joint
    "E3CF", "E3TF",    # E-3 Sentry AWACS
    "CP14",             # CP-140 Aurora (Canada)
    "P3",               # P-3C Orion
    "RQ4", "GLHK",     # RQ-4 Global Hawk
    "MQ9",              # MQ-9 Reaper
}

# --- Government operator patterns (Step 2) ---

GOV_OPERATOR_PATTERNS = [
    r"Coast Guard",
    r"Kystvakt",            # Norwegian Coast Guard
    r"Kustbevakning",       # Swedish Coast Guard
    r"Politi",              # Norwegian/Danish police
    r"Politiet",
    r"Rajavartio",          # Finnish Border Guard
    r"Sysselm",            # Governor of Svalbard
    r"Lufttransport",      # Operates Dornier 228s for Norwegian Coast Guard
    r"Border Guard",
    r"Försvarsmakten",     # Swedish Armed Forces
    r"Forsvaret",          # Norwegian Armed Forces
    r"Puolustusvoimat",    # Finnish Defence Forces
    r"Flyvevåbnet",        # Danish Air Force (sometimes civil-registered)
    r"Politiflyg",         # Swedish police aviation
    r"Rikspolisstyrelsen", # Swedish National Police Board
]

GOV_RE = re.compile("|".join(GOV_OPERATOR_PATTERNS), re.IGNORECASE)

# All Nordic ICAO ranges (broader, for gov operator matching)
NORDIC_BROAD_RANGES = [
    (0x478000, 0x47FFFF, "Norway"),
    (0x4A8000, 0x4AFFFF, "Sweden"),
    (0x458000, 0x45FFFF, "Denmark"),
    (0x460000, 0x467FFF, "Finland"),
    # Civil ranges too — gov aircraft often registered as civil
    (0x470000, 0x477FFF, "Norway civil"),
    (0x4A0000, 0x4A7FFF, "Sweden civil"),
    (0x450000, 0x457FFF, "Denmark civil"),
    (0x468000, 0x46FFFF, "Finland civil"),
]


def in_ranges(hex_val, ranges):
    for lo, hi, _ in ranges:
        if lo <= hex_val <= hi:
            return True
    return False


def get_country(hex_val, ranges):
    for lo, hi, country in ranges:
        if lo <= hex_val <= hi:
            return country
    return None


def main():
    results = []
    stats = {"step1_nordic_mil": 0, "step2_gov_ops": 0, "step3_nato_patrol": 0}

    with open(INPUT) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ac = json.loads(line)
            except json.JSONDecodeError:
                continue

            icao = ac.get("icao", "")
            try:
                hex_val = int(icao, 16)
            except (ValueError, TypeError):
                continue

            mil = ac.get("mil", False)
            ownop = ac.get("ownop") or ""
            icaotype = ac.get("icaotype") or ""
            category = None

            # Step 1: Nordic military
            if mil and in_ranges(hex_val, NORDIC_RANGES):
                category = "nordic_military"
                country = get_country(hex_val, NORDIC_RANGES)
                stats["step1_nordic_mil"] += 1

            # Step 2: Nordic government operators (civil-registered)
            elif ownop and GOV_RE.search(ownop) and in_ranges(hex_val, NORDIC_BROAD_RANGES):
                category = "nordic_government"
                country = get_country(hex_val, NORDIC_BROAD_RANGES)
                stats["step2_gov_ops"] += 1

            # Step 3: NATO patrol aircraft over Baltic/Nordic
            elif mil and in_ranges(hex_val, NATO_MIL_RANGES) and icaotype in NATO_PATROL_TYPES:
                category = "nato_patrol"
                country = get_country(hex_val, NATO_MIL_RANGES)
                stats["step3_nato_patrol"] += 1

            else:
                continue

            ac["_category"] = category
            ac["_country"] = country
            results.append(ac)

    # Sort by category then icao
    results.sort(key=lambda x: (x["_category"], x["icao"]))

    with open(OUTPUT, "w") as f:
        for ac in results:
            f.write(json.dumps(ac) + "\n")

    print(f"Filtered {len(results)} aircraft → {OUTPUT}")
    print(f"  Step 1 — Nordic military (mil=True + Nordic hex):  {stats['step1_nordic_mil']}")
    print(f"  Step 2 — Nordic government operators:              {stats['step2_gov_ops']}")
    print(f"  Step 3 — NATO patrol (US/UK/DE mil + patrol type): {stats['step3_nato_patrol']}")

    # Print sample
    print("\n--- Sample entries ---")
    for ac in results[:20]:
        print(f"  {ac['icao']}  {ac.get('reg','?'):>10}  {ac.get('icaotype',''):>6}  "
              f"{ac['_category']:<20}  {ac['_country']:<20}  {ac.get('ownop','')}")


if __name__ == "__main__":
    main()
