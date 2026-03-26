"""Graph schema definition and initialization for FalkorDB.

Defines node types, edge types, and creates indexes in FalkorDB.
The graph is schema-less — this module enforces conventions through
the graph builder code and provides initialization/validation utilities.

Node types:
    Vessel, Company, Person, ClassSociety, FlagState, PIClub

Edge types (all temporal with from_date/to_date):
    OWNED_BY, MANAGED_BY, CLASSED_BY, FLAGGED_AS, INSURED_BY,
    DIRECTED_BY, STS_PARTNER
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("graph-builder.schema")

# ---------------------------------------------------------------------------
# Node type definitions (documentation + validation reference)
# ---------------------------------------------------------------------------

NODE_TYPES = {
    "Vessel": {
        "key": "imo",
        "attributes": [
            "imo", "name", "mmsi", "ship_type", "gross_tonnage", "build_year",
            "score", "classification",  # green/yellow/red/blacklisted
            "last_psc_date", "last_psc_port", "deficiency_count",
            "ism_deficiency", "detained",
            "last_seen_date", "last_seen_lat", "last_seen_lon",
            "sanctions_programs", "sanctioned_date",
            "topics",  # shadow_fleet, sanction, etc.
        ],
    },
    "Company": {
        "key": "name",
        "attributes": [
            "name", "jurisdiction", "incorporation_date",
            "ism_company_number", "company_type",  # owner/ism_manager/operator
            "opensanctions_id",
        ],
    },
    "Person": {
        "key": "name",
        "attributes": [
            "name", "nationality", "date_of_birth", "opensanctions_id",
        ],
    },
    "ClassSociety": {
        "key": "name",
        "attributes": ["name", "iacs_member"],
    },
    "FlagState": {
        "key": "iso_code",
        "attributes": ["name", "iso_code", "paris_mou_list"],  # white/grey/black
    },
    "PIClub": {
        "key": "name",
        "attributes": ["name", "ig_member"],
    },
}

# ---------------------------------------------------------------------------
# Edge type definitions
# ---------------------------------------------------------------------------

EDGE_TYPES = {
    "OWNED_BY": {
        "from_labels": ["Vessel", "Company"],
        "to_labels": ["Company", "Person"],
        "temporal": True,
        "attributes": ["from_date", "to_date"],
    },
    "MANAGED_BY": {
        "from_labels": ["Vessel"],
        "to_labels": ["Company"],
        "temporal": True,
        "attributes": ["from_date", "to_date"],
    },
    "CLASSED_BY": {
        "from_labels": ["Vessel"],
        "to_labels": ["ClassSociety"],
        "temporal": True,
        "attributes": ["from_date", "to_date", "status"],  # active/suspended/withdrawn
    },
    "FLAGGED_AS": {
        "from_labels": ["Vessel"],
        "to_labels": ["FlagState"],
        "temporal": True,
        "attributes": ["from_date", "to_date"],
    },
    "INSURED_BY": {
        "from_labels": ["Vessel"],
        "to_labels": ["PIClub"],
        "temporal": True,
        "attributes": ["from_date", "to_date"],
    },
    "DIRECTED_BY": {
        "from_labels": ["Company"],
        "to_labels": ["Person"],
        "temporal": True,
        "attributes": ["from_date", "to_date"],
    },
    "STS_PARTNER": {
        "from_labels": ["Vessel"],
        "to_labels": ["Vessel"],
        "temporal": False,
        "attributes": ["event_date", "latitude", "longitude", "duration_hours"],
    },
}


# ---------------------------------------------------------------------------
# IG P&I Club seed data
# ---------------------------------------------------------------------------

IG_PI_CLUBS = [
    "American Steamship Owners Mutual Protection and Indemnity Association",
    "Assuranceforeningen Skuld",
    "Britannia Steam Ship Insurance Association",
    "The Japan Ship Owners' Mutual Protection & Indemnity Association",
    "The London Steam-Ship Owners' Mutual Insurance Association",
    "North of England Protecting & Indemnity Association",
    "The Shipowners' Mutual Protection and Indemnity Association (Luxembourg)",
    "The Standard Club",
    "Steamship Mutual Underwriting Association",
    "The Swedish Club",
    "United Kingdom Mutual Steam Ship Assurance Association",
    "The West of England Ship Owners Mutual Insurance Association",
    "NorthStandard",  # 2023 merger of North and Standard
]

# ---------------------------------------------------------------------------
# Graph initialization
# ---------------------------------------------------------------------------


def init_graph(graph: Any) -> dict[str, int]:
    """Create indexes in FalkorDB for the Heimdal graph schema.

    Args:
        graph: FalkorDB graph handle (from get_graph())

    Returns:
        Dict with counts of indexes created.
    """
    indexes_created = 0

    # Node indexes for fast lookups
    index_specs = [
        ("Vessel", "imo"),
        ("Vessel", "mmsi"),
        ("Vessel", "name"),
        ("Company", "name"),
        ("Company", "opensanctions_id"),
        ("Company", "ism_company_number"),
        ("Person", "name"),
        ("Person", "opensanctions_id"),
        ("ClassSociety", "name"),
        ("FlagState", "iso_code"),
        ("FlagState", "name"),
        ("PIClub", "name"),
    ]

    for label, prop in index_specs:
        try:
            graph.create_node_range_index(label, prop)
            indexes_created += 1
            logger.info("index_created", extra={"label": label, "property": prop})
        except Exception as e:
            if "already indexed" in str(e).lower() or "already exists" in str(e).lower():
                logger.debug("index_exists", extra={"label": label, "property": prop})
            else:
                logger.warning(
                    "index_create_failed",
                    extra={"label": label, "property": prop, "error": str(e)},
                )

    # Seed IG P&I Clubs
    clubs_created = _seed_pi_clubs(graph)

    return {
        "indexes_created": indexes_created,
        "pi_clubs_seeded": clubs_created,
    }


def _seed_pi_clubs(graph: Any) -> int:
    """Create PIClub nodes for the 13 International Group members."""
    created = 0
    for club_name in IG_PI_CLUBS:
        result = graph.query(
            "MERGE (p:PIClub {name: $name}) "
            "ON CREATE SET p.ig_member = true "
            "RETURN p.name",
            {"name": club_name},
        )
        if result.nodes_created > 0:
            created += 1
    logger.info("pi_clubs_seeded: %d created, %d total", created, len(IG_PI_CLUBS))
    return created
