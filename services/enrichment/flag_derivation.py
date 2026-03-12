"""Flag state derivation and mismatch detection.

Derives a vessel's flag state from its MMSI (via MID lookup), compares
it with flags from other sources (GFW, GISIS), and maintains a flag
history tracking changes over time.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.constants import MID_TO_FLAG

logger = logging.getLogger("enrichment.flag_derivation")


def extract_mid(mmsi: int) -> int | None:
    """Extract the Maritime Identification Digits (first 3 digits) from an MMSI.

    Args:
        mmsi: 9-digit MMSI number.

    Returns:
        3-digit MID integer, or None if MMSI is invalid.
    """
    if not isinstance(mmsi, int) or mmsi < 100000000 or mmsi > 999999999:
        return None
    return mmsi // 1000000


def mid_to_flag(mid: int) -> str | None:
    """Look up the ISO country code for a given MID.

    Args:
        mid: 3-digit Maritime Identification Digits.

    Returns:
        ISO 3166-1 alpha-2 country code, or None if MID not found.
    """
    return MID_TO_FLAG.get(mid)


def derive_flag_from_mmsi(mmsi: int) -> str | None:
    """Derive the flag state country code from an MMSI number.

    Args:
        mmsi: 9-digit MMSI number.

    Returns:
        ISO 3166-1 alpha-2 country code, or None if cannot be derived.
    """
    mid = extract_mid(mmsi)
    if mid is None:
        return None
    return mid_to_flag(mid)


def detect_flag_mismatches(
    *,
    mid_flag: str | None = None,
    gfw_flag: str | None = None,
    gisis_flag: str | None = None,
) -> list[dict[str, Any]]:
    """Compare flags from multiple sources and detect mismatches.

    Args:
        mid_flag: Flag derived from MMSI MID lookup.
        gfw_flag: Flag reported by Global Fishing Watch.
        gisis_flag: Flag from IMO GISIS (if available).

    Returns:
        List of mismatch dicts, each with 'source_a', 'flag_a',
        'source_b', 'flag_b' describing the disagreement.
    """
    mismatches: list[dict[str, Any]] = []
    sources = []
    if mid_flag:
        sources.append(("mid", mid_flag))
    if gfw_flag:
        sources.append(("gfw", gfw_flag))
    if gisis_flag:
        sources.append(("gisis", gisis_flag))

    for i in range(len(sources)):
        for j in range(i + 1, len(sources)):
            src_a, flag_a = sources[i]
            src_b, flag_b = sources[j]
            if flag_a != flag_b:
                mismatches.append({
                    "source_a": src_a,
                    "flag_a": flag_a,
                    "source_b": src_b,
                    "flag_b": flag_b,
                })

    return mismatches


def update_flag_history(
    current_history: list[dict[str, Any]],
    flag: str,
    timestamp: datetime | None = None,
) -> list[dict[str, Any]]:
    """Update the flag history with a new observation.

    If the most recent entry has the same flag, update its last_seen.
    If the flag is different, add a new entry.

    Args:
        current_history: Existing flag history list (may be empty).
        flag: The flag country code observed now.
        timestamp: When this flag was observed. Defaults to now (UTC).

    Returns:
        Updated flag history list.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    ts_str = timestamp.isoformat()

    # Make a copy to avoid mutating the input
    history = [entry.copy() for entry in current_history]

    if history and history[-1].get("flag") == flag:
        # Same flag as last entry — just update last_seen
        history[-1]["last_seen"] = ts_str
    else:
        # New flag — add a new entry
        history.append({
            "flag": flag,
            "first_seen": ts_str,
            "last_seen": ts_str,
        })

    return history


def derive_and_compare(
    mmsi: int,
    *,
    gfw_flag: str | None = None,
    gisis_flag: str | None = None,
    current_flag_history: list[dict[str, Any]] | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Full flag derivation pipeline for a vessel.

    Derives the MID flag, detects mismatches, and updates flag history.

    Args:
        mmsi: 9-digit MMSI number.
        gfw_flag: Flag from GFW data.
        gisis_flag: Flag from GISIS data (optional).
        current_flag_history: Existing flag history from vessel profile.
        timestamp: Observation timestamp.

    Returns:
        Dict with 'mid_flag', 'mismatches', 'flag_history', and
        'primary_flag' (the best available flag).
    """
    if current_flag_history is None:
        current_flag_history = []
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    mid_flag = derive_flag_from_mmsi(mmsi)

    mismatches = detect_flag_mismatches(
        mid_flag=mid_flag,
        gfw_flag=gfw_flag,
        gisis_flag=gisis_flag,
    )

    # Primary flag priority: GFW > GISIS > MID-derived
    primary_flag = gfw_flag or gisis_flag or mid_flag

    # Update flag history with the primary flag
    flag_history = current_flag_history
    if primary_flag:
        flag_history = update_flag_history(
            current_flag_history, primary_flag, timestamp
        )

    return {
        "mid_flag": mid_flag,
        "mismatches": mismatches,
        "flag_history": flag_history,
        "primary_flag": primary_flag,
    }
