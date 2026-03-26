"""OpenSanctions FTM entity graph extractor.

Streams the OpenSanctions default.json NDJSON file line-by-line and extracts:
- Entity nodes (Vessel, Company, Person, Organization, LegalEntity)
- Relationship edges (Ownership, Directorship, Sanction)
- Vessel links (IMO/MMSI to entity_id mapping)

The extractor yields batches of parsed records for the caller to persist.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger("opensanctions.extractor")

# FTM schemas of primary interest (for stats breakdown)
PRIMARY_ENTITY_SCHEMAS = {"Vessel", "Company", "Person", "Organization", "LegalEntity"}

# We store ALL non-relationship entities as nodes so that relationship FKs
# always resolve. Entities outside PRIMARY_ENTITY_SCHEMAS (e.g. Address,
# Identification, Security) may have incomplete data but are needed as
# relationship endpoints.

# FTM schemas that represent relationships
RELATIONSHIP_SCHEMAS = {
    "Ownership": "ownership",
    "Directorship": "directorship",
    "Sanction": "sanction",
    "Family": "family",
    "Associate": "associate",
    "UnknownLink": "associate",
    "Representation": "associate",
}

# Ownership: owner → asset
# Directorship: director → organization
# Sanction: entity → (program stored in properties)
RELATIONSHIP_FIELD_MAP = {
    "Ownership": ("owner", "asset"),
    "Directorship": ("director", "organization"),
    "Sanction": ("entity", None),  # sanction has entity but no second entity — we use the sanction itself
    "Family": ("person", "relative"),
    "Associate": ("person", "associate"),
    "UnknownLink": ("subject", "object"),
    "Representation": ("agent", "client"),
}

DEFAULT_BATCH_SIZE = 5000


@dataclass
class ExtractorStats:
    """Counters for the extraction run."""
    entities_by_type: dict[str, int] = field(default_factory=dict)
    relationships_by_type: dict[str, int] = field(default_factory=dict)
    vessel_links: int = 0
    lines_processed: int = 0
    lines_skipped: int = 0
    elapsed_seconds: float = 0.0

    @property
    def total_entities(self) -> int:
        return sum(self.entities_by_type.values())

    @property
    def total_relationships(self) -> int:
        return sum(self.relationships_by_type.values())

    def log_summary(self) -> None:
        logger.info(
            "Extraction complete in %.1fs: %d entities, %d relationships, %d vessel links",
            self.elapsed_seconds, self.total_entities, self.total_relationships, self.vessel_links,
        )
        for schema, count in sorted(self.entities_by_type.items()):
            logger.info("  Entity type %s: %d", schema, count)
        for rel_type, count in sorted(self.relationships_by_type.items()):
            logger.info("  Relationship type %s: %d", rel_type, count)


@dataclass
class EntityRecord:
    """Parsed entity ready for DB insert."""
    entity_id: str
    schema_type: str
    name: str | None
    properties: dict[str, Any]
    topics: list[str]
    target: bool
    dataset: str | None


@dataclass
class RelationshipRecord:
    """Parsed relationship ready for DB insert."""
    rel_type: str
    source_entity_id: str
    target_entity_id: str
    properties: dict[str, Any]


@dataclass
class VesselLinkRecord:
    """Links a Vessel entity to IMO/MMSI."""
    entity_id: str
    imo: int | None
    mmsi: int | None
    confidence: float
    match_method: str


@dataclass
class ExtractionBatch:
    """A batch of extracted records."""
    entities: list[EntityRecord] = field(default_factory=list)
    relationships: list[RelationshipRecord] = field(default_factory=list)
    vessel_links: list[VesselLinkRecord] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.entities) + len(self.relationships) + len(self.vessel_links)


def _first_prop(props: dict[str, Any], key: str) -> str | None:
    """Get first value from FTM properties array, or None."""
    vals = props.get(key, [])
    if vals and isinstance(vals, list):
        return str(vals[0])
    return None


def _parse_int(val: str | None) -> int | None:
    """Parse an integer from a string, stripping non-numeric prefixes."""
    if not val:
        return None
    cleaned = re.sub(r"^[A-Za-z\s]*", "", val.strip())
    try:
        return int(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_entity(raw: dict[str, Any]) -> EntityRecord:
    """Parse an FTM entity dict into an EntityRecord."""
    props = raw.get("properties", {})
    name = _first_prop(props, "name")
    topics = raw.get("properties", {}).get("topics", [])
    if not isinstance(topics, list):
        topics = []
    # Also check top-level datasets for topic hints
    target = raw.get("target", False)
    dataset_list = raw.get("datasets", [])
    dataset = dataset_list[0] if dataset_list else None

    return EntityRecord(
        entity_id=raw["id"],
        schema_type=raw["schema"],
        name=name,
        properties=props,
        topics=topics,
        target=bool(target),
        dataset=dataset,
    )


def _parse_relationship(raw: dict[str, Any]) -> RelationshipRecord | None:
    """Parse an FTM relationship entity into a RelationshipRecord."""
    schema = raw.get("schema", "")
    rel_type = RELATIONSHIP_SCHEMAS.get(schema)
    if rel_type is None:
        return None

    props = raw.get("properties", {})
    field_map = RELATIONSHIP_FIELD_MAP.get(schema)
    if not field_map:
        return None

    source_field, target_field = field_map

    source_ids = props.get(source_field, [])
    source_id = source_ids[0] if source_ids else None

    if target_field:
        target_ids = props.get(target_field, [])
        target_id = target_ids[0] if target_ids else None
    else:
        # For Sanction: entity is the sanctioned entity, we store it as source
        # and we don't have a second entity — skip if no source
        target_id = None

    if not source_id:
        return None

    # For Sanction without target, we can't create a relationship edge.
    # Store sanction info on the entity's topics instead.
    if not target_id:
        return None

    # Build properties dict from interesting fields
    rel_props: dict[str, Any] = {}
    for key in ("role", "startDate", "endDate", "program", "authority",
                "listingDate", "status", "percentage", "summary"):
        val = _first_prop(props, key)
        if val:
            rel_props[key] = val

    return RelationshipRecord(
        rel_type=rel_type,
        source_entity_id=source_id,
        target_entity_id=target_id,
        properties=rel_props,
    )


def _extract_vessel_links(raw: dict[str, Any]) -> list[VesselLinkRecord]:
    """Extract IMO/MMSI links from a Vessel entity."""
    entity_id = raw["id"]
    props = raw.get("properties", {})
    links: list[VesselLinkRecord] = []

    # IMO numbers
    for imo_raw in props.get("imoNumber", []):
        imo = _parse_int(str(imo_raw))
        if imo:
            links.append(VesselLinkRecord(
                entity_id=entity_id,
                imo=imo,
                mmsi=None,
                confidence=1.0,
                match_method="imo_exact",
            ))

    # MMSI numbers
    for mmsi_raw in props.get("mmsiNumber", []) + props.get("mmsi", []):
        mmsi = _parse_int(str(mmsi_raw))
        if mmsi:
            links.append(VesselLinkRecord(
                entity_id=entity_id,
                imo=None,
                mmsi=mmsi,
                confidence=0.9,
                match_method="mmsi_exact",
            ))

    return links


def stream_extract(
    filepath: str | Path,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Generator[tuple[ExtractionBatch, ExtractorStats], None, None]:
    """Stream-extract the OpenSanctions NDJSON file in batches.

    Yields (batch, running_stats) tuples. The caller persists each batch.
    The final yield contains the complete stats.

    Args:
        filepath: Path to the default.json NDJSON file.
        batch_size: Number of records per batch.

    Yields:
        (ExtractionBatch, ExtractorStats) — batch of records and running stats.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"OpenSanctions data file not found: {filepath}")

    stats = ExtractorStats()
    batch = ExtractionBatch()
    start_time = time.monotonic()

    # First pass: collect all entity IDs so we can validate relationship references
    # We skip this for performance — instead we collect entities that are referenced
    # by relationships but missing, and the DB FK constraint handles it.

    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            stats.lines_processed += 1

            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                stats.lines_skipped += 1
                continue

            schema = raw.get("schema", "")
            entity_id = raw.get("id")
            if not entity_id:
                stats.lines_skipped += 1
                continue

            # Relationship edge (check first — relationships are also entities in FTM)
            if schema in RELATIONSHIP_SCHEMAS:
                rel = _parse_relationship(raw)
                if rel:
                    batch.relationships.append(rel)
                    stats.relationships_by_type[rel.rel_type] = (
                        stats.relationships_by_type.get(rel.rel_type, 0) + 1
                    )
            # Entity node — store ALL non-relationship schemas so FK references resolve
            else:
                record = _parse_entity(raw)
                batch.entities.append(record)
                stats.entities_by_type[schema] = stats.entities_by_type.get(schema, 0) + 1

                # Vessel links
                if schema == "Vessel":
                    links = _extract_vessel_links(raw)
                    batch.vessel_links.extend(links)
                    stats.vessel_links += len(links)

            # Flush batch
            if batch.size >= batch_size:
                stats.elapsed_seconds = time.monotonic() - start_time
                yield batch, stats
                batch = ExtractionBatch()

    # Final batch
    if batch.size > 0:
        stats.elapsed_seconds = time.monotonic() - start_time
        yield batch, stats

    stats.elapsed_seconds = time.monotonic() - start_time
    stats.log_summary()
