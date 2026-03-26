"""Tests for 025_opensanctions_graph.sql migration file.

Validates SQL structure via string/regex matching — no DB connection needed.
"""

import re
from pathlib import Path

import pytest

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "db" / "migrations" / "025_opensanctions_graph.sql"


@pytest.fixture(scope="module")
def sql_content() -> str:
    """Load the migration SQL file."""
    assert MIGRATION_PATH.exists(), f"Migration file not found: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text()


# ---------- 1. Basic syntax ----------

def test_sql_file_parses(sql_content: str):
    """Validate BEGIN/COMMIT wrapper and non-trivial length."""
    assert "BEGIN;" in sql_content
    assert "COMMIT;" in sql_content
    assert len(sql_content) > 500


# ---------- 2. CREATE TABLE statements ----------

EXPECTED_TABLES = ["os_entities", "os_relationships", "os_vessel_links"]


@pytest.mark.parametrize("table_name", EXPECTED_TABLES)
def test_create_table_exists(sql_content: str, table_name: str):
    pattern = rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{table_name}\s*\("
    assert re.search(pattern, sql_content, re.IGNORECASE), (
        f"Missing CREATE TABLE IF NOT EXISTS for {table_name}"
    )


# ---------- 3. Column checks ----------

def test_os_entities_columns(sql_content: str):
    """os_entities has all required columns."""
    block = _extract_table_block(sql_content, "os_entities")
    for col in ["entity_id", "schema_type", "name", "properties", "topics",
                "target", "first_seen", "last_seen", "dataset"]:
        assert col in block, f"os_entities missing column: {col}"


def test_os_relationships_columns(sql_content: str):
    """os_relationships has all required columns."""
    block = _extract_table_block(sql_content, "os_relationships")
    for col in ["rel_type", "source_entity_id", "target_entity_id",
                "properties", "first_seen", "last_seen"]:
        assert col in block, f"os_relationships missing column: {col}"


def test_os_vessel_links_columns(sql_content: str):
    """os_vessel_links has all required columns."""
    block = _extract_table_block(sql_content, "os_vessel_links")
    for col in ["entity_id", "imo", "mmsi", "confidence", "match_method"]:
        assert col in block, f"os_vessel_links missing column: {col}"


# ---------- 4. Foreign key checks ----------

def test_relationships_fk_to_entities(sql_content: str):
    """os_relationships has FKs referencing os_entities(entity_id)."""
    block = _extract_table_block(sql_content, "os_relationships")
    fk_matches = re.findall(r"REFERENCES\s+os_entities\s*\(\s*entity_id\s*\)", block, re.IGNORECASE)
    assert len(fk_matches) >= 2, (
        f"Expected at least 2 FKs to os_entities(entity_id), found {len(fk_matches)}"
    )


def test_vessel_links_fk_to_entities(sql_content: str):
    """os_vessel_links has FK referencing os_entities(entity_id)."""
    block = _extract_table_block(sql_content, "os_vessel_links")
    assert re.search(r"REFERENCES\s+os_entities\s*\(\s*entity_id\s*\)", block, re.IGNORECASE), (
        "os_vessel_links missing FK to os_entities(entity_id)"
    )


# ---------- 5. Index checks ----------

EXPECTED_INDEXES = [
    "idx_os_entities_schema_type",
    "idx_os_entities_topics",
    "idx_os_entities_name",
    "idx_os_relationships_source",
    "idx_os_relationships_target",
    "idx_os_relationships_rel_type",
    "idx_os_vessel_links_imo",
    "idx_os_vessel_links_mmsi",
    "idx_os_vessel_links_entity",
]


@pytest.mark.parametrize("index_name", EXPECTED_INDEXES)
def test_index_exists(sql_content: str, index_name: str):
    pattern = rf"CREATE\s+(UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+{index_name}\b"
    assert re.search(pattern, sql_content, re.IGNORECASE), (
        f"Missing CREATE INDEX for {index_name}"
    )


def test_gin_index_on_topics(sql_content: str):
    """Topics array uses GIN index for efficient filtering."""
    assert re.search(r"USING\s+GIN\s*\(\s*topics\s*\)", sql_content, re.IGNORECASE), (
        "Missing GIN index on topics"
    )


# ---------- 6. Data type checks ----------

def test_entity_id_is_text_pk(sql_content: str):
    """os_entities.entity_id is TEXT PRIMARY KEY."""
    block = _extract_table_block(sql_content, "os_entities")
    assert re.search(r"entity_id\s+TEXT\s+PRIMARY\s+KEY", block, re.IGNORECASE)


def test_os_vessel_links_has_composite_pk(sql_content: str):
    """os_vessel_links uses (entity_id, match_method) as composite PK."""
    block = _extract_table_block(sql_content, "os_vessel_links")
    assert re.search(r"PRIMARY\s+KEY\s*\(\s*entity_id\s*,\s*match_method\s*\)", block, re.IGNORECASE)


def test_properties_is_jsonb(sql_content: str):
    """Both os_entities and os_relationships use JSONB for properties."""
    for table in ["os_entities", "os_relationships"]:
        block = _extract_table_block(sql_content, table)
        assert re.search(r"properties\s+JSONB", block, re.IGNORECASE), (
            f"{table}.properties should be JSONB"
        )


def test_topics_is_text_array(sql_content: str):
    """os_entities.topics is TEXT[]."""
    block = _extract_table_block(sql_content, "os_entities")
    assert re.search(r"topics\s+TEXT\s*\[\s*\]", block, re.IGNORECASE)


# ---------- helpers ----------

def _extract_table_block(sql: str, table_name: str) -> str:
    """Extract the CREATE TABLE block for a given table name."""
    match = re.search(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{table_name}\s*\((.*?)\);",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"Could not find CREATE TABLE block for {table_name}"
    return match.group(1)
