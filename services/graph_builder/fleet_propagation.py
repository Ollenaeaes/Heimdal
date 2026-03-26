"""Fleet Risk Propagation via FalkorDB Graph (Story 7).

Propagates risk through ownership/management graph for signals:
- A10: ISM company fleet risk (weight 2) — same ISM manager as blacklisted vessel
- B4: Owner fleet risk (weight 3) — same owner as blacklisted vessel

Propagation rules:
- One-directional: blacklisted/red vessels propagate TO siblings
- No cascade: a vessel flagged via propagation does NOT trigger further propagation
- Runs AFTER individual vessel scoring, BEFORE final classification
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("fleet-propagation")


@dataclass
class PropagationSignal:
    """A signal produced by fleet risk propagation."""
    signal_id: str
    weight: float
    details: dict
    source_data: str


def find_managed_siblings(graph: Any, imo: int) -> list[dict]:
    """Find all vessels managed by the same ISM company as the given vessel.

    Returns list of dicts: [{imo, name, classification}, ...]
    """
    result = graph.query(
        """
        MATCH (v:Vessel {imo: $imo})-[:MANAGED_BY]->(c:Company)<-[:MANAGED_BY]-(sibling:Vessel)
        WHERE sibling.imo <> $imo
        RETURN sibling.imo AS imo, sibling.name AS name, sibling.classification AS classification
        """,
        {"imo": imo},
    )
    return [
        {"imo": row[0], "name": row[1], "classification": row[2]}
        for row in result.result_set
    ]


def find_owned_siblings(graph: Any, imo: int) -> list[dict]:
    """Find all vessels owned by the same Company as the given vessel.

    Checks 1-hop ownership: Vessel→Company→Vessel.
    Does NOT traverse Company→Company chains (kept simple per spec).
    """
    result = graph.query(
        """
        MATCH (v:Vessel {imo: $imo})-[:OWNED_BY]->(c:Company)<-[:OWNED_BY]-(sibling:Vessel)
        WHERE sibling.imo <> $imo
        RETURN sibling.imo AS imo, sibling.name AS name, sibling.classification AS classification
        """,
        {"imo": imo},
    )
    return [
        {"imo": row[0], "name": row[1], "classification": row[2]}
        for row in result.result_set
    ]


def evaluate_a10(graph: Any, imo: int) -> list[PropagationSignal]:
    """A10: ISM company fleet risk — sibling vessel is blacklisted/red.

    Weight: 2
    """
    siblings = find_managed_siblings(graph, imo)
    risky = [s for s in siblings if s["classification"] in ("blacklisted", "red")]

    if not risky:
        return []

    return [PropagationSignal(
        signal_id="A10",
        weight=2,
        details={
            "reason": "ISM company manages a blacklisted/red vessel",
            "risky_siblings": [
                {"imo": s["imo"], "name": s["name"], "classification": s["classification"]}
                for s in risky
            ],
        },
        source_data="falkordb_graph",
    )]


def evaluate_b4(graph: Any, imo: int) -> list[PropagationSignal]:
    """B4: Owner fleet risk — owner's other vessel is blacklisted/red.

    Weight: 3
    """
    siblings = find_owned_siblings(graph, imo)
    risky = [s for s in siblings if s["classification"] in ("blacklisted", "red")]

    if not risky:
        return []

    return [PropagationSignal(
        signal_id="B4",
        weight=3,
        details={
            "reason": "Same owner as a blacklisted/red vessel",
            "risky_siblings": [
                {"imo": s["imo"], "name": s["name"], "classification": s["classification"]}
                for s in risky
            ],
        },
        source_data="falkordb_graph",
    )]


def propagate_fleet_risk(graph: Any, imo: int) -> list[PropagationSignal]:
    """Run both A10 and B4 fleet propagation for a vessel.

    This should be called AFTER individual vessel scoring and BEFORE
    final classification.
    """
    signals = []
    signals.extend(evaluate_a10(graph, imo))
    signals.extend(evaluate_b4(graph, imo))
    return signals
