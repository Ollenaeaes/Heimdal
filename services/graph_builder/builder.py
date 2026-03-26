"""Graph Builder — Static Data Sources (Story 3).

Reads from PostgreSQL (Paris MoU, OpenSanctions, IACS) and builds the
Heimdal graph in FalkorDB. Uses sync psycopg2 for batch reads and
MERGE-based Cypher for idempotent writes.

Usage:
    python -m services.graph_builder.builder

Environment:
    DATABASE_URL — PostgreSQL connection string (async format stripped automatically)
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import psycopg2
import psycopg2.extras

from services.graph_builder.schema import IG_PI_CLUBS, init_graph
from shared.config import settings
from shared.db.graph import get_graph, close_graph

logger = logging.getLogger("graph-builder")

# Batch size for UNWIND operations
BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# Stats tracking
# ---------------------------------------------------------------------------

@dataclass
class BuildStats:
    """Tracks nodes/edges created and transitions detected."""
    nodes: dict[str, int] = field(default_factory=lambda: {
        "Vessel": 0, "Company": 0, "Person": 0,
        "ClassSociety": 0, "FlagState": 0, "PIClub": 0,
    })
    edges: dict[str, int] = field(default_factory=lambda: {
        "OWNED_BY": 0, "MANAGED_BY": 0, "CLASSED_BY": 0,
        "FLAGGED_AS": 0, "INSURED_BY": 0, "DIRECTED_BY": 0,
        "STS_PARTNER": 0,
    })
    transitions: int = 0
    elapsed: float = 0.0

    def log_summary(self) -> None:
        logger.info("=== Graph Build Summary ===")
        logger.info("Nodes: %s", self.nodes)
        logger.info("Edges: %s", self.edges)
        logger.info("Transitions detected: %d", self.transitions)
        logger.info("Elapsed: %.1fs", self.elapsed)


# ---------------------------------------------------------------------------
# Helper: sync PostgreSQL connection
# ---------------------------------------------------------------------------

def _get_sync_dsn() -> str:
    """Convert async DATABASE_URL to sync psycopg2 DSN."""
    url = os.environ.get("DATABASE_URL", settings.database_url.get_secret_value())
    # Strip +asyncpg driver suffix
    url = re.sub(r"postgresql\+asyncpg://", "postgresql://", url)
    return url


def _get_pg_connection():
    """Return a psycopg2 connection using RealDictCursor."""
    return psycopg2.connect(_get_sync_dsn())


# ---------------------------------------------------------------------------
# GraphBuilder
# ---------------------------------------------------------------------------

class GraphBuilder:
    """Builds the Heimdal graph from static PostgreSQL data sources."""

    def __init__(self, graph: Any | None = None, pg_conn: Any | None = None):
        """Initialize with optional graph handle and PG connection.

        Args:
            graph: FalkorDB graph handle. If None, uses shared.db.graph.get_graph().
            pg_conn: psycopg2 connection. If None, creates one from DATABASE_URL.
        """
        self.graph = graph or get_graph()
        self._owns_pg = pg_conn is None
        self.pg = pg_conn or _get_pg_connection()
        self.stats = BuildStats()

    def close(self) -> None:
        if self._owns_pg and self.pg:
            self.pg.close()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def build_all(self) -> BuildStats:
        """Run all static data source builders in order."""
        t0 = time.time()

        # Initialize schema indexes
        init_graph(self.graph)

        # Process in dependency order
        self.build_from_paris_mou()
        self.build_from_opensanctions()
        self.build_from_iacs()

        self.stats.elapsed = time.time() - t0
        self.stats.log_summary()
        return self.stats

    # ------------------------------------------------------------------
    # Paris MoU
    # ------------------------------------------------------------------

    def build_from_paris_mou(self) -> None:
        """Build graph from psc_inspections and psc_flag_performance."""
        logger.info("Building from Paris MoU inspections...")

        # Load flag performance list
        flag_list = self._load_flag_performance()

        # Load all inspections grouped by IMO, ordered by date
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT imo, ship_name, flag_state, ship_type, gross_tonnage,
                       inspection_date, detained, deficiency_count, ism_deficiency,
                       ro_at_inspection, pi_provider_at_inspection, pi_is_ig_member,
                       ism_company_imo, ism_company_name
                FROM psc_inspections
                ORDER BY imo, inspection_date ASC
            """)
            rows = cur.fetchall()

        if not rows:
            logger.info("No Paris MoU inspections found")
            return

        # Group by IMO
        vessels: dict[int, list[dict]] = {}
        for row in rows:
            imo = row["imo"]
            if imo not in vessels:
                vessels[imo] = []
            vessels[imo].append(dict(row))

        # Process each vessel's inspection history
        vessel_batch = []
        for imo, inspections in vessels.items():
            latest = inspections[-1]
            vessel_batch.append({
                "imo": imo,
                "name": latest["ship_name"],
                "ship_type": latest["ship_type"],
                "gross_tonnage": latest["gross_tonnage"],
                "last_psc_date": str(latest["inspection_date"]) if latest["inspection_date"] else None,
                "deficiency_count": latest["deficiency_count"],
                "ism_deficiency": latest["ism_deficiency"],
                "detained": latest["detained"],
            })

        # Batch MERGE vessels
        self._merge_vessels_batch(vessel_batch)

        # Process temporal edges for each vessel
        for imo, inspections in vessels.items():
            self._process_psc_temporal_edges(imo, inspections, flag_list)

        logger.info("Paris MoU: processed %d vessels from %d inspections",
                     len(vessels), len(rows))

    def _load_flag_performance(self) -> dict[str, str]:
        """Load psc_flag_performance into a dict: iso_code -> list_status."""
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT iso_code, list_status FROM psc_flag_performance")
            return {row["iso_code"]: row["list_status"] for row in cur.fetchall()}

    def _merge_vessels_batch(self, batch: list[dict]) -> None:
        """MERGE Vessel nodes in batches."""
        for i in range(0, len(batch), BATCH_SIZE):
            chunk = batch[i:i + BATCH_SIZE]
            result = self.graph.query(
                """
                UNWIND $batch AS row
                MERGE (v:Vessel {imo: row.imo})
                ON CREATE SET
                    v.name = row.name,
                    v.ship_type = row.ship_type,
                    v.gross_tonnage = row.gross_tonnage,
                    v.last_psc_date = row.last_psc_date,
                    v.deficiency_count = row.deficiency_count,
                    v.ism_deficiency = row.ism_deficiency,
                    v.detained = row.detained
                ON MATCH SET
                    v.name = COALESCE(row.name, v.name),
                    v.ship_type = COALESCE(row.ship_type, v.ship_type),
                    v.gross_tonnage = COALESCE(row.gross_tonnage, v.gross_tonnage),
                    v.last_psc_date = row.last_psc_date,
                    v.deficiency_count = row.deficiency_count,
                    v.ism_deficiency = row.ism_deficiency,
                    v.detained = row.detained
                """,
                {"batch": chunk},
            )
            self.stats.nodes["Vessel"] += result.nodes_created

    def _process_psc_temporal_edges(
        self, imo: int, inspections: list[dict], flag_list: dict[str, str]
    ) -> None:
        """Process temporal edges for a vessel's inspection history.

        Detects transitions in class society, flag, insurer, and ISM company
        across inspections. Old edges get to_date set, new edges are created.
        """
        prev_ro = None
        prev_flag = None
        prev_pi = None
        prev_ism = None

        for insp in inspections:
            insp_date = str(insp["inspection_date"]) if insp["inspection_date"] else None
            if not insp_date:
                continue

            # --- CLASSED_BY (RO at inspection) ---
            ro = insp.get("ro_at_inspection")
            if ro:
                if prev_ro and prev_ro != ro:
                    # Transition: close old edge, create new
                    self._close_temporal_edge(imo, "CLASSED_BY", "ClassSociety", "name", prev_ro, insp_date)
                    self.stats.transitions += 1
                self._merge_classed_by(imo, ro, insp_date)
                prev_ro = ro

            # --- FLAGGED_AS ---
            flag = insp.get("flag_state")
            if flag:
                if prev_flag and prev_flag != flag:
                    self._close_temporal_edge(imo, "FLAGGED_AS", "FlagState", "iso_code", prev_flag, insp_date)
                    self.stats.transitions += 1
                list_status = flag_list.get(flag)
                self._merge_flagged_as(imo, flag, insp_date, list_status)
                prev_flag = flag

            # --- INSURED_BY (PI provider) ---
            pi = insp.get("pi_provider_at_inspection")
            if pi:
                if prev_pi and prev_pi != pi:
                    self._close_temporal_edge(imo, "INSURED_BY", "PIClub", "name", prev_pi, insp_date)
                    self.stats.transitions += 1
                ig_member = insp.get("pi_is_ig_member", False)
                self._merge_insured_by(imo, pi, insp_date, ig_member)
                prev_pi = pi

            # --- MANAGED_BY (ISM company) ---
            ism_name = insp.get("ism_company_name")
            ism_imo = insp.get("ism_company_imo")
            if ism_name:
                ism_key = ism_imo or ism_name  # use IMO if available, else name
                if prev_ism and prev_ism != ism_key:
                    # Close old edge — find by company name or imo
                    self._close_managed_by(imo, prev_ism, insp_date)
                    self.stats.transitions += 1
                self._merge_managed_by(imo, ism_name, ism_imo, insp_date)
                prev_ism = ism_key

    def _merge_classed_by(self, imo: int, ro_name: str, from_date: str) -> None:
        """MERGE ClassSociety node and CLASSED_BY edge."""
        result = self.graph.query(
            """
            MERGE (v:Vessel {imo: $imo})
            MERGE (cs:ClassSociety {name: $ro_name})
            MERGE (v)-[e:CLASSED_BY {from_date: $from_date}]->(cs)
            ON CREATE SET e.status = 'active'
            """,
            {"imo": imo, "ro_name": ro_name, "from_date": from_date},
        )
        self.stats.nodes["ClassSociety"] += result.nodes_created
        self.stats.edges["CLASSED_BY"] += result.relationships_created

    def _merge_flagged_as(self, imo: int, iso_code: str, from_date: str, list_status: str | None) -> None:
        """MERGE FlagState node and FLAGGED_AS edge."""
        result = self.graph.query(
            """
            MERGE (v:Vessel {imo: $imo})
            MERGE (f:FlagState {iso_code: $iso_code})
            ON CREATE SET f.paris_mou_list = $list_status
            ON MATCH SET f.paris_mou_list = COALESCE($list_status, f.paris_mou_list)
            MERGE (v)-[e:FLAGGED_AS {from_date: $from_date}]->(f)
            """,
            {"imo": imo, "iso_code": iso_code, "from_date": from_date, "list_status": list_status},
        )
        self.stats.nodes["FlagState"] += result.nodes_created
        self.stats.edges["FLAGGED_AS"] += result.relationships_created

    def _merge_insured_by(self, imo: int, pi_name: str, from_date: str, ig_member: bool) -> None:
        """MERGE PIClub node and INSURED_BY edge."""
        result = self.graph.query(
            """
            MERGE (v:Vessel {imo: $imo})
            MERGE (p:PIClub {name: $pi_name})
            ON CREATE SET p.ig_member = $ig_member
            MERGE (v)-[e:INSURED_BY {from_date: $from_date}]->(p)
            """,
            {"imo": imo, "pi_name": pi_name, "from_date": from_date, "ig_member": ig_member},
        )
        self.stats.nodes["PIClub"] += result.nodes_created
        self.stats.edges["INSURED_BY"] += result.relationships_created

    def _merge_managed_by(self, imo: int, company_name: str, company_imo: str | None, from_date: str) -> None:
        """MERGE Company node (ISM manager) and MANAGED_BY edge."""
        result = self.graph.query(
            """
            MERGE (v:Vessel {imo: $imo})
            MERGE (c:Company {name: $company_name})
            ON CREATE SET c.ism_company_number = $company_imo,
                          c.company_type = 'ism_manager'
            MERGE (v)-[e:MANAGED_BY {from_date: $from_date}]->(c)
            """,
            {"imo": imo, "company_name": company_name, "company_imo": company_imo, "from_date": from_date},
        )
        self.stats.nodes["Company"] += result.nodes_created
        self.stats.edges["MANAGED_BY"] += result.relationships_created

    def _close_temporal_edge(
        self, imo: int, edge_type: str, target_label: str,
        target_key: str, target_value: str, to_date: str,
    ) -> None:
        """Set to_date on an existing temporal edge where to_date is null."""
        self.graph.query(
            f"""
            MATCH (v:Vessel {{imo: $imo}})-[e:{edge_type}]->(t:{target_label} {{{target_key}: $target_value}})
            WHERE e.to_date IS NULL
            SET e.to_date = $to_date
            """,
            {"imo": imo, "target_value": target_value, "to_date": to_date},
        )

    def _close_managed_by(self, imo: int, prev_ism_key: str, to_date: str) -> None:
        """Close MANAGED_BY edge. prev_ism_key can be company IMO or name."""
        # Try matching by ism_company_number first, then by name
        self.graph.query(
            """
            MATCH (v:Vessel {imo: $imo})-[e:MANAGED_BY]->(c:Company)
            WHERE e.to_date IS NULL
              AND (c.ism_company_number = $key OR c.name = $key)
            SET e.to_date = $to_date
            """,
            {"imo": imo, "key": prev_ism_key, "to_date": to_date},
        )

    # ------------------------------------------------------------------
    # OpenSanctions
    # ------------------------------------------------------------------

    def build_from_opensanctions(self) -> None:
        """Build graph from os_entities, os_relationships, os_vessel_links."""
        logger.info("Building from OpenSanctions...")

        # Step 1: Load vessel links (entity_id → IMO mapping)
        vessel_links = self._load_vessel_links()
        if not vessel_links:
            logger.info("No OpenSanctions vessel links found")
            return

        # Step 2: Load and process entities
        entity_imos = self._load_os_entities(vessel_links)

        # Step 3: Load and process relationships
        self._load_os_relationships(vessel_links, entity_imos)

        logger.info("OpenSanctions: processed %d vessel links", len(vessel_links))

    def _load_vessel_links(self) -> dict[str, int]:
        """Load os_vessel_links: entity_id → IMO."""
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT entity_id, imo
                FROM os_vessel_links
                WHERE imo IS NOT NULL
            """)
            return {row["entity_id"]: int(row["imo"]) for row in cur.fetchall()}

    def _load_os_entities(self, vessel_links: dict[str, int]) -> dict[str, int | None]:
        """Load os_entities and create graph nodes.

        Returns dict mapping entity_id to IMO (for vessel entities) or None.
        """
        entity_imos: dict[str, int | None] = {}

        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Only load entities connected to vessels (via vessel_links or relationships)
            # This avoids loading 3M+ unrelated entities
            cur.execute("""
                SELECT DISTINCT e.entity_id, e.schema_type, e.name, e.properties, e.topics, e.target
                FROM os_entities e
                WHERE e.entity_id IN (
                    SELECT entity_id FROM os_vessel_links
                    UNION
                    SELECT source_entity_id FROM os_relationships
                    WHERE target_entity_id IN (SELECT entity_id FROM os_vessel_links)
                       OR source_entity_id IN (SELECT entity_id FROM os_vessel_links)
                    UNION
                    SELECT target_entity_id FROM os_relationships
                    WHERE target_entity_id IN (SELECT entity_id FROM os_vessel_links)
                       OR source_entity_id IN (SELECT entity_id FROM os_vessel_links)
                )
            """)
            rows = cur.fetchall()
            logger.info("OpenSanctions: loaded %d vessel-connected entities (of %d total)",
                        len(rows), 0)  # avoid counting total for performance

        # Classify entities
        vessel_batch = []
        company_batch = []
        person_batch = []

        for row in rows:
            eid = row["entity_id"]
            schema = row["schema_type"]
            name = row["name"]
            props = row["properties"] or {}
            topics = row["topics"] or []
            target = row["target"]

            if schema == "Vessel":
                imo = vessel_links.get(eid)
                entity_imos[eid] = imo
                if imo:
                    vessel_data = {
                        "imo": imo,
                        "name": name,
                        "opensanctions_id": eid,
                        "topics": topics,
                        "target": target,
                    }
                    # Extract sanctions info if target
                    if target and topics:
                        vessel_data["sanctions_programs"] = topics
                    vessel_batch.append(vessel_data)

            elif schema in ("Company", "Organization", "LegalEntity"):
                entity_imos[eid] = None
                jurisdiction = None
                if isinstance(props, dict):
                    jurisdictions = props.get("jurisdiction", [])
                    if isinstance(jurisdictions, list) and jurisdictions:
                        jurisdiction = jurisdictions[0]
                    elif isinstance(jurisdictions, str):
                        jurisdiction = jurisdictions
                company_batch.append({
                    "name": name,
                    "opensanctions_id": eid,
                    "jurisdiction": jurisdiction,
                })

            elif schema == "Person":
                entity_imos[eid] = None
                nationality = None
                dob = None
                if isinstance(props, dict):
                    nats = props.get("nationality", [])
                    if isinstance(nats, list) and nats:
                        nationality = nats[0]
                    elif isinstance(nats, str):
                        nationality = nats
                    dobs = props.get("birthDate", [])
                    if isinstance(dobs, list) and dobs:
                        dob = dobs[0]
                    elif isinstance(dobs, str):
                        dob = dobs
                person_batch.append({
                    "name": name,
                    "opensanctions_id": eid,
                    "nationality": nationality,
                    "date_of_birth": dob,
                })

        # Batch create nodes
        self._merge_os_vessels(vessel_batch)
        self._merge_os_companies(company_batch)
        self._merge_os_persons(person_batch)

        return entity_imos

    def _merge_os_vessels(self, batch: list[dict]) -> None:
        """MERGE vessel nodes from OpenSanctions (update with OS-specific attributes)."""
        for i in range(0, len(batch), BATCH_SIZE):
            chunk = batch[i:i + BATCH_SIZE]
            result = self.graph.query(
                """
                UNWIND $batch AS row
                MERGE (v:Vessel {imo: row.imo})
                ON CREATE SET
                    v.name = row.name,
                    v.opensanctions_id = row.opensanctions_id
                ON MATCH SET
                    v.opensanctions_id = row.opensanctions_id,
                    v.name = COALESCE(v.name, row.name)
                SET v.topics = row.topics
                """,
                {"batch": chunk},
            )
            self.stats.nodes["Vessel"] += result.nodes_created

        # Handle sanctions_programs separately for target entities
        sanctioned = [v for v in batch if v.get("sanctions_programs")]
        for v in sanctioned:
            self.graph.query(
                """
                MATCH (v:Vessel {imo: $imo})
                SET v.sanctions_programs = $programs,
                    v.classification = 'blacklisted'
                """,
                {"imo": v["imo"], "programs": v["sanctions_programs"]},
            )

    def _merge_os_companies(self, batch: list[dict]) -> None:
        """MERGE Company nodes from OpenSanctions."""
        for i in range(0, len(batch), BATCH_SIZE):
            chunk = batch[i:i + BATCH_SIZE]
            result = self.graph.query(
                """
                UNWIND $batch AS row
                MERGE (c:Company {opensanctions_id: row.opensanctions_id})
                ON CREATE SET
                    c.name = row.name,
                    c.jurisdiction = row.jurisdiction
                ON MATCH SET
                    c.name = COALESCE(row.name, c.name),
                    c.jurisdiction = COALESCE(row.jurisdiction, c.jurisdiction)
                """,
                {"batch": chunk},
            )
            self.stats.nodes["Company"] += result.nodes_created

    def _merge_os_persons(self, batch: list[dict]) -> None:
        """MERGE Person nodes from OpenSanctions."""
        for i in range(0, len(batch), BATCH_SIZE):
            chunk = batch[i:i + BATCH_SIZE]
            result = self.graph.query(
                """
                UNWIND $batch AS row
                MERGE (p:Person {opensanctions_id: row.opensanctions_id})
                ON CREATE SET
                    p.name = row.name,
                    p.nationality = row.nationality,
                    p.date_of_birth = row.date_of_birth
                ON MATCH SET
                    p.name = COALESCE(row.name, p.name),
                    p.nationality = COALESCE(row.nationality, p.nationality),
                    p.date_of_birth = COALESCE(row.date_of_birth, p.date_of_birth)
                """,
                {"batch": chunk},
            )
            self.stats.nodes["Person"] += result.nodes_created

    def _load_os_relationships(self, vessel_links: dict[str, int], entity_imos: dict[str, int | None]) -> None:
        """Load os_relationships and create edges (only vessel-connected)."""
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT rel_type, source_entity_id, target_entity_id, properties
                FROM os_relationships
                WHERE source_entity_id IN (SELECT entity_id FROM os_vessel_links)
                   OR target_entity_id IN (SELECT entity_id FROM os_vessel_links)
            """)
            rows = cur.fetchall()
        logger.info("OpenSanctions: loaded %d vessel-connected relationships", len(rows))

        for row in rows:
            rel_type = row["rel_type"]
            source_id = row["source_entity_id"]
            target_id = row["target_entity_id"]
            props = row["properties"] or {}

            # Skip relationships where both entities are unknown
            if source_id not in entity_imos and target_id not in entity_imos:
                continue

            if rel_type == "ownership":
                self._create_ownership_edge(source_id, target_id, entity_imos, vessel_links, props)
            elif rel_type == "directorship":
                self._create_directorship_edge(source_id, target_id, entity_imos, props)
            elif rel_type == "sanction":
                # Sanctions are attributes on Vessel, not edges — handled in _merge_os_vessels
                pass

    def _create_ownership_edge(
        self, source_id: str, target_id: str,
        entity_imos: dict[str, int | None],
        vessel_links: dict[str, int],
        props: dict,
    ) -> None:
        """Create OWNED_BY edge. Source entity is owned by target entity."""
        from_date = None
        if isinstance(props, dict):
            dates = props.get("startDate", [])
            if isinstance(dates, list) and dates:
                from_date = dates[0]
            elif isinstance(dates, str):
                from_date = dates

        source_imo = entity_imos.get(source_id)
        target_imo = entity_imos.get(target_id)

        # Vessel → Company/Person ownership
        if source_imo is not None:
            result = self.graph.query(
                """
                MATCH (v:Vessel {imo: $source_imo})
                MATCH (owner) WHERE owner.opensanctions_id = $target_id
                MERGE (v)-[e:OWNED_BY]->(owner)
                ON CREATE SET e.from_date = $from_date
                """,
                {"source_imo": source_imo, "target_id": target_id, "from_date": from_date},
            )
            self.stats.edges["OWNED_BY"] += result.relationships_created
        else:
            # Company → Company/Person ownership
            result = self.graph.query(
                """
                MATCH (source) WHERE source.opensanctions_id = $source_id
                MATCH (target) WHERE target.opensanctions_id = $target_id
                MERGE (source)-[e:OWNED_BY]->(target)
                ON CREATE SET e.from_date = $from_date
                """,
                {"source_id": source_id, "target_id": target_id, "from_date": from_date},
            )
            self.stats.edges["OWNED_BY"] += result.relationships_created

    def _create_directorship_edge(
        self, source_id: str, target_id: str,
        entity_imos: dict[str, int | None],
        props: dict,
    ) -> None:
        """Create DIRECTED_BY edge. Source company is directed by target person."""
        from_date = None
        if isinstance(props, dict):
            dates = props.get("startDate", [])
            if isinstance(dates, list) and dates:
                from_date = dates[0]
            elif isinstance(dates, str):
                from_date = dates

        result = self.graph.query(
            """
            MATCH (source) WHERE source.opensanctions_id = $source_id
            MATCH (target) WHERE target.opensanctions_id = $target_id
            MERGE (source)-[e:DIRECTED_BY]->(target)
            ON CREATE SET e.from_date = $from_date
            """,
            {"source_id": source_id, "target_id": target_id, "from_date": from_date},
        )
        self.stats.edges["DIRECTED_BY"] += result.relationships_created

    # ------------------------------------------------------------------
    # IACS
    # ------------------------------------------------------------------

    def build_from_iacs(self) -> None:
        """Build/update graph from iacs_vessels_current."""
        logger.info("Building from IACS...")

        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT imo, ship_name, class_society, status,
                       date_of_latest_status
                FROM iacs_vessels_current
            """)
            rows = cur.fetchall()

        if not rows:
            logger.info("No IACS data found")
            return

        for row in rows:
            imo = row["imo"]
            class_society = row["class_society"]
            status_raw = (row["status"] or "").strip()
            status_date = str(row["date_of_latest_status"]) if row["date_of_latest_status"] else None

            if not class_society:
                continue

            # Map IACS status to edge status
            if status_raw in ("Delivered", "Reinstated"):
                edge_status = "active"
            elif status_raw == "Suspended":
                edge_status = "suspended"
            elif status_raw == "Withdrawn":
                edge_status = "withdrawn"
            else:
                edge_status = "active"  # default

            if edge_status == "withdrawn":
                # Close the CLASSED_BY edge
                self.graph.query(
                    """
                    MERGE (v:Vessel {imo: $imo})
                    MERGE (cs:ClassSociety {name: $class_society})
                    ON CREATE SET cs.iacs_member = true
                    MERGE (v)-[e:CLASSED_BY]->(cs)
                    ON CREATE SET e.from_date = $status_date,
                                  e.to_date = $status_date,
                                  e.status = 'withdrawn'
                    ON MATCH SET e.to_date = CASE WHEN e.status <> 'withdrawn' THEN $status_date ELSE e.to_date END,
                                 e.status = 'withdrawn'
                    """,
                    {"imo": imo, "class_society": class_society, "status_date": status_date},
                )
                self.stats.edges["CLASSED_BY"] += 1
            else:
                # Active or suspended — ensure edge exists with correct status
                result = self.graph.query(
                    """
                    MERGE (v:Vessel {imo: $imo})
                    ON CREATE SET v.name = $ship_name
                    MERGE (cs:ClassSociety {name: $class_society})
                    ON CREATE SET cs.iacs_member = true
                    MERGE (v)-[e:CLASSED_BY]->(cs)
                    ON CREATE SET e.from_date = $status_date,
                                  e.status = $edge_status
                    ON MATCH SET e.status = $edge_status
                    """,
                    {
                        "imo": imo, "ship_name": row["ship_name"],
                        "class_society": class_society,
                        "status_date": status_date, "edge_status": edge_status,
                    },
                )
                self.stats.nodes["Vessel"] += result.nodes_created
                self.stats.nodes["ClassSociety"] += result.nodes_created
                self.stats.edges["CLASSED_BY"] += result.relationships_created

        logger.info("IACS: processed %d vessels", len(rows))

    # ------------------------------------------------------------------
    # AIS-Derived Data (Story 4)
    # ------------------------------------------------------------------

    def enrich_from_ais(self) -> None:
        """Enrich graph with AIS-derived data from vessel_profiles and gfw_events.

        Updates Vessel nodes with last_seen data and creates STS_PARTNER edges
        from GFW encounter events and sts_proximity anomalies.

        This is read-only on PostgreSQL — only writes to FalkorDB.
        """
        logger.info("Enriching graph from AIS data...")
        self._update_vessel_positions()
        self._create_sts_from_gfw()
        self._create_sts_from_anomalies()
        logger.info("AIS enrichment complete")

    def _update_vessel_positions(self) -> None:
        """Update Vessel nodes with last_seen data from vessel_profiles."""
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT mmsi, imo, last_lat, last_lon, last_position_time
                FROM vessel_profiles
                WHERE imo IS NOT NULL
                  AND last_lat IS NOT NULL
                  AND last_lon IS NOT NULL
            """)
            rows = cur.fetchall()

        if not rows:
            logger.info("No vessel profiles with positions found")
            return

        # Batch update in chunks
        updated = 0
        for i in range(0, len(rows), BATCH_SIZE):
            chunk = [
                {
                    "imo": row["imo"],
                    "mmsi": str(row["mmsi"]),
                    "last_seen_lat": row["last_lat"],
                    "last_seen_lon": row["last_lon"],
                    "last_seen_date": str(row["last_position_time"]) if row["last_position_time"] else None,
                }
                for row in rows[i:i + BATCH_SIZE]
            ]
            result = self.graph.query(
                """
                UNWIND $batch AS row
                MATCH (v:Vessel {imo: row.imo})
                SET v.mmsi = row.mmsi,
                    v.last_seen_lat = row.last_seen_lat,
                    v.last_seen_lon = row.last_seen_lon,
                    v.last_seen_date = row.last_seen_date
                """,
                {"batch": chunk},
            )
            updated += result.properties_set

        logger.info("AIS positions: updated %d vessel properties from %d profiles", updated, len(rows))

    def _create_sts_from_gfw(self) -> None:
        """Create STS_PARTNER edges from GFW encounter events."""
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT g.mmsi, g.encounter_mmsi, g.start_time, g.lat, g.lon,
                       EXTRACT(EPOCH FROM (g.end_time - g.start_time)) / 3600.0 AS duration_hours,
                       vp1.imo AS imo1, vp2.imo AS imo2
                FROM gfw_events g
                JOIN vessel_profiles vp1 ON vp1.mmsi = g.mmsi
                LEFT JOIN vessel_profiles vp2 ON vp2.mmsi = g.encounter_mmsi
                WHERE g.event_type = 'encounter'
                  AND g.encounter_mmsi IS NOT NULL
                  AND vp1.imo IS NOT NULL
            """)
            rows = cur.fetchall()

        sts_count = 0
        for row in rows:
            imo1 = row["imo1"]
            imo2 = row["imo2"]
            if not imo1 or not imo2:
                continue

            result = self.graph.query(
                """
                MERGE (v1:Vessel {imo: $imo1})
                MERGE (v2:Vessel {imo: $imo2})
                MERGE (v1)-[e:STS_PARTNER {event_date: $event_date}]->(v2)
                ON CREATE SET
                    e.latitude = $lat,
                    e.longitude = $lon,
                    e.duration_hours = $duration_hours
                """,
                {
                    "imo1": imo1,
                    "imo2": imo2,
                    "event_date": str(row["start_time"].date()) if row["start_time"] else None,
                    "lat": row["lat"],
                    "lon": row["lon"],
                    "duration_hours": round(row["duration_hours"], 1) if row["duration_hours"] else None,
                },
            )
            sts_count += result.relationships_created

        self.stats.edges["STS_PARTNER"] += sts_count
        logger.info("GFW encounters: created %d STS_PARTNER edges from %d events", sts_count, len(rows))

    def _create_sts_from_anomalies(self) -> None:
        """Create STS_PARTNER edges from sts_proximity anomaly events."""
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT a.mmsi, a.details, a.created_at,
                       vp.imo
                FROM anomaly_events a
                JOIN vessel_profiles vp ON vp.mmsi = a.mmsi
                WHERE a.rule_id = 'sts_proximity'
                  AND vp.imo IS NOT NULL
                  AND a.details IS NOT NULL
            """)
            rows = cur.fetchall()

        sts_count = 0
        for row in rows:
            details = row["details"] or {}
            partner_mmsi = details.get("partner_mmsi") or details.get("nearby_mmsi")
            if not partner_mmsi:
                continue

            # Look up partner IMO
            with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT imo FROM vessel_profiles WHERE mmsi = %s AND imo IS NOT NULL",
                    (int(partner_mmsi),),
                )
                partner = cur.fetchone()

            if not partner:
                continue

            imo1 = row["imo"]
            imo2 = partner["imo"]
            event_date = str(row["created_at"].date()) if row["created_at"] else None
            lat = details.get("lat") or details.get("latitude")
            lon = details.get("lon") or details.get("longitude")

            result = self.graph.query(
                """
                MERGE (v1:Vessel {imo: $imo1})
                MERGE (v2:Vessel {imo: $imo2})
                MERGE (v1)-[e:STS_PARTNER {event_date: $event_date}]->(v2)
                ON CREATE SET
                    e.latitude = $lat,
                    e.longitude = $lon,
                    e.source = 'sts_proximity'
                """,
                {
                    "imo1": imo1,
                    "imo2": imo2,
                    "event_date": event_date,
                    "lat": lat,
                    "lon": lon,
                },
            )
            sts_count += result.relationships_created

        self.stats.edges["STS_PARTNER"] += sts_count
        logger.info("STS proximity: created %d STS_PARTNER edges from %d anomalies", sts_count, len(rows))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    builder = GraphBuilder()
    try:
        builder.build_all()
    finally:
        builder.close()


if __name__ == "__main__":
    main()
