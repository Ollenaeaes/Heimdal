"""Signal-Based Scoring Engine — Score Calculator (Story 6).

Pure function that computes a vessel risk score and classification
from a list of signals. Applies override rules for specific signal
combinations.

Usage:
    from services.graph_builder.score_calculator import compute_score
    from services.graph_builder.signal_scorer import Signal

    signals = [Signal("A1", 3), Signal("B5", 1)]
    total_score, classification = compute_score(signals)
    # → (4, "yellow")
"""

from __future__ import annotations

from services.graph_builder.signal_scorer import Signal


# ---------------------------------------------------------------------------
# Classification thresholds
# ---------------------------------------------------------------------------

def _classify(score: float) -> str:
    """Map a raw score to a classification tier.

    0-3  → green
    4-5  → yellow
    6-8  → red
    ≥9   → red (strong multi-source pattern)
    """
    if score <= 3:
        return "green"
    elif score <= 5:
        return "yellow"
    else:
        return "red"


_TIER_ORDER = {"green": 0, "yellow": 1, "red": 2, "blacklisted": 3}


def _escalate(current: str, minimum: str) -> str:
    """Escalate classification to at least *minimum*."""
    if _TIER_ORDER.get(minimum, 0) > _TIER_ORDER.get(current, 0):
        return minimum
    return current


# ---------------------------------------------------------------------------
# Override rules
# ---------------------------------------------------------------------------

def _apply_overrides(signals: list[Signal], classification: str) -> str:
    """Apply override rules that force a minimum classification.

    Override rules:
    - B1 alone → minimum yellow
    - (D3 or D4) + (A7 or A6) → minimum red
    - D6 (STS with blacklisted/red) → minimum red
    - C3 + A1 → minimum yellow
    - A10 or B4 → minimum yellow
    """
    signal_ids = {s.signal_id for s in signals}

    # B1 alone → minimum yellow
    if "B1" in signal_ids:
        classification = _escalate(classification, "yellow")

    # (D3 or D4) + (A7 or A6) → minimum red
    has_d3_or_d4 = bool(signal_ids & {"D3", "D4"})
    has_a7_or_a6 = bool(signal_ids & {"A7", "A6"})
    if has_d3_or_d4 and has_a7_or_a6:
        classification = _escalate(classification, "red")

    # D6 (STS with blacklisted/red) → minimum red
    if "D6" in signal_ids:
        classification = _escalate(classification, "red")

    # C3 + A1 → minimum yellow
    if "C3" in signal_ids and "A1" in signal_ids:
        classification = _escalate(classification, "yellow")

    # A10 or B4 → minimum yellow
    if signal_ids & {"A10", "B4"}:
        classification = _escalate(classification, "yellow")

    return classification


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_score(
    signals: list[Signal],
    is_sanctioned: bool = False,
) -> tuple[float, str]:
    """Compute vessel risk score and classification from signals.

    Args:
        signals: List of Signal objects from the signal evaluator.
        is_sanctioned: If True, the vessel is directly sanctioned in
            OpenSanctions (target=True) and is classified as blacklisted
            regardless of score.

    Returns:
        Tuple of (total_score, classification).
        classification is one of: "green", "yellow", "red", "blacklisted"
    """
    # Sanctioned vessels are always blacklisted
    if is_sanctioned:
        total = sum(s.weight for s in signals)
        return (total, "blacklisted")

    # Sum weights
    total = sum(s.weight for s in signals)

    # Base classification from thresholds
    classification = _classify(total)

    # Apply override rules
    classification = _apply_overrides(signals, classification)

    return (total, classification)
