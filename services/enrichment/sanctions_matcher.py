"""OpenSanctions bulk matching engine.

Loads the OpenSanctions default.json dataset into an in-memory index
keyed by IMO, MMSI, and normalized vessel name, then matches vessel
profiles against the index using exact and fuzzy matching.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import Levenshtein

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.config import settings

logger = logging.getLogger("enrichment.sanctions_matcher")

# Maximum Levenshtein distance for fuzzy name matching
MAX_NAME_DISTANCE = 2

# Default path to the OpenSanctions dataset
DEFAULT_DATA_PATH = os.environ.get(
    "OPENSANCTIONS_DATA_PATH", "./data/opensanctions"
)


def normalize_name(name: str) -> str:
    """Normalize a vessel name for fuzzy comparison.

    Lowercase, strip non-alphanumeric characters (except spaces),
    collapse multiple spaces into one, and strip leading/trailing whitespace.
    """
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


class SanctionsIndex:
    """In-memory lookup index for OpenSanctions vessel entities."""

    def __init__(self) -> None:
        self.by_imo: dict[str, list[dict[str, Any]]] = {}
        self.by_mmsi: dict[str, list[dict[str, Any]]] = {}
        self.by_name: dict[str, list[dict[str, Any]]] = {}
        # Keep all normalized names for fuzzy search
        self.all_names: list[str] = []
        self.loaded = False

    def load(self, data_path: str | None = None) -> int:
        """Load the OpenSanctions NDJSON dataset into the index.

        Args:
            data_path: Directory containing default.json. Falls back to
                       OPENSANCTIONS_DATA_PATH env var or ./data/opensanctions.

        Returns:
            Number of vessel entities indexed.
        """
        path = Path(data_path or DEFAULT_DATA_PATH) / "default.json"
        if not path.exists():
            logger.warning("OpenSanctions data file not found: %s", path)
            return 0

        count = 0
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entity = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not self._is_vessel_entity(entity):
                    continue
                self._index_entity(entity)
                count += 1

        self.all_names = list(self.by_name.keys())
        self.loaded = True
        logger.info("Loaded %d vessel entities from OpenSanctions", count)
        return count

    def _is_vessel_entity(self, entity: dict[str, Any]) -> bool:
        """Check if an entity is a vessel (has IMO, MMSI, or is Vessel schema)."""
        schema = entity.get("schema", "")
        props = entity.get("properties", {})
        # Accept Vessel schema or any entity with maritime identifiers
        if schema == "Vessel":
            return True
        if props.get("imoNumber") or props.get("mmsiNumber") or props.get("mmsi"):
            return True
        return False

    def _extract_programs(self, entity: dict[str, Any]) -> list[str]:
        """Extract sanctions program names from an entity."""
        props = entity.get("properties", {})
        # OpenSanctions uses 'topics' to indicate sanctions
        topics = props.get("topics", [])
        # Also check for 'sanctions' in datasets
        datasets = entity.get("datasets", [])
        programs = []
        if "sanction" in topics:
            programs.append("sanctions")
        for ds in datasets:
            if isinstance(ds, str) and ds not in programs:
                programs.append(ds)
        if not programs:
            programs = ["unknown"]
        return programs

    def _make_entry(self, entity: dict[str, Any]) -> dict[str, Any]:
        """Create a compact entry for the index."""
        return {
            "entity_id": entity.get("id", ""),
            "programs": self._extract_programs(entity),
            "properties": entity.get("properties", {}),
        }

    def _index_entity(self, entity: dict[str, Any]) -> None:
        """Add a single entity to the lookup indices."""
        entry = self._make_entry(entity)
        props = entity.get("properties", {})

        # Index by IMO numbers — strip "IMO" prefix if present
        for imo in props.get("imoNumber", []):
            imo_str = str(imo).strip()
            # OpenSanctions often stores as "IMO9321172", normalize to digits
            imo_str = re.sub(r"^IMO\s*", "", imo_str, flags=re.IGNORECASE)
            if imo_str:
                self.by_imo.setdefault(imo_str, []).append(entry)

        # Index by MMSI numbers — OpenSanctions uses "mmsi" key for Vessel schema
        for mmsi in props.get("mmsiNumber", []) + props.get("mmsi", []):
            mmsi_str = str(mmsi).strip()
            if mmsi_str:
                self.by_mmsi.setdefault(mmsi_str, []).append(entry)

        # Index by normalized vessel names
        for name in props.get("name", []):
            normalized = normalize_name(name)
            if normalized:
                self.by_name.setdefault(normalized, []).append(entry)


def match_vessel(
    index: SanctionsIndex,
    *,
    imo: int | str | None = None,
    mmsi: int | str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Match a vessel against the sanctions index.

    Checks in order: exact IMO (confidence 1.0), exact MMSI (confidence 0.9),
    fuzzy name (confidence 0.7). Returns a sanctions_status dict.

    Args:
        index: Loaded SanctionsIndex.
        imo: Vessel IMO number.
        mmsi: Vessel MMSI number.
        name: Vessel name.

    Returns:
        A dict with 'matches' key containing list of match objects, or
        empty dict if no matches found.
    """
    matches: list[dict[str, Any]] = []

    # 1. Exact IMO match (highest confidence)
    if imo is not None:
        imo_str = str(imo).strip()
        if imo_str in index.by_imo:
            for entry in index.by_imo[imo_str]:
                matches.append({
                    "entity_id": entry["entity_id"],
                    "program": entry["programs"][0] if entry["programs"] else "unknown",
                    "confidence": 1.0,
                    "matched_field": "imo",
                })

    # 2. Exact MMSI match
    if mmsi is not None:
        mmsi_str = str(mmsi).strip()
        if mmsi_str in index.by_mmsi:
            for entry in index.by_mmsi[mmsi_str]:
                # Avoid duplicates if same entity already matched by IMO
                existing_ids = {m["entity_id"] for m in matches}
                if entry["entity_id"] not in existing_ids:
                    matches.append({
                        "entity_id": entry["entity_id"],
                        "program": entry["programs"][0] if entry["programs"] else "unknown",
                        "confidence": 0.9,
                        "matched_field": "mmsi",
                    })

    # 3. Exact name match only (fuzzy matching produces too many false positives
    # for short vessel names like "VICI" matching "VANI")
    if name is not None:
        normalized_query = normalize_name(name)
        if normalized_query and normalized_query in index.by_name:
            existing_ids = {m["entity_id"] for m in matches}
            for entry in index.by_name[normalized_query]:
                if entry["entity_id"] not in existing_ids:
                    matches.append({
                        "entity_id": entry["entity_id"],
                        "program": entry["programs"][0] if entry["programs"] else "unknown",
                        "confidence": 0.8,
                        "matched_field": "name",
                    })
                    existing_ids.add(entry["entity_id"])

    if not matches:
        return {}

    return {"matches": matches}
