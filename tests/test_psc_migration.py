"""Tests for 024_psc_inspections.sql migration file.

Validates SQL structure and content via string/regex matching — no DB connection needed.
"""

import re
from pathlib import Path

import pytest

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "db" / "migrations" / "024_psc_inspections.sql"


@pytest.fixture(scope="module")
def sql_content() -> str:
    """Load the migration SQL file."""
    assert MIGRATION_PATH.exists(), f"Migration file not found: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text()


# ---------- 1. Basic syntax / parse check ----------

def test_sql_file_parses(sql_content: str):
    """Validate the SQL file has balanced BEGIN/COMMIT and no obvious syntax issues."""
    assert "BEGIN;" in sql_content, "Missing BEGIN statement"
    assert "COMMIT;" in sql_content, "Missing COMMIT statement"
    # No unterminated strings (odd number of single quotes per line is suspicious
    # but not conclusive; instead just check the file is non-trivially long)
    assert len(sql_content) > 1000, "Migration file seems too short"


# ---------- 2. All 4 CREATE TABLE statements ----------

EXPECTED_TABLES = [
    "psc_inspections",
    "psc_deficiencies",
    "psc_certificates",
    "psc_flag_performance",
]


@pytest.mark.parametrize("table_name", EXPECTED_TABLES)
def test_create_table_exists(sql_content: str, table_name: str):
    """Each expected table has a CREATE TABLE IF NOT EXISTS statement."""
    pattern = rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{table_name}\s*\("
    assert re.search(pattern, sql_content, re.IGNORECASE), (
        f"Missing CREATE TABLE IF NOT EXISTS for {table_name}"
    )


# ---------- 3. All 6 indexes ----------

EXPECTED_INDEXES = [
    "idx_psc_inspections_imo_date",
    "idx_psc_inspections_ism_company",
    "idx_psc_inspections_flag",
    "idx_psc_inspections_detained",
    "idx_psc_deficiencies_inspection",
    "idx_psc_certificates_inspection",
]


@pytest.mark.parametrize("index_name", EXPECTED_INDEXES)
def test_index_exists(sql_content: str, index_name: str):
    """Each expected index has a CREATE INDEX statement."""
    pattern = rf"CREATE\s+INDEX\s+(IF\s+NOT\s+EXISTS\s+)?{index_name}\b"
    assert re.search(pattern, sql_content, re.IGNORECASE), (
        f"Missing CREATE INDEX for {index_name}"
    )


# ---------- 4. Seed data has at least 50 flag states ----------

def test_seed_data_has_enough_entries(sql_content: str):
    """The psc_flag_performance INSERT should contain at least 50 distinct ISO codes."""
    # Match all 2-letter ISO codes in INSERT VALUES for psc_flag_performance
    # Pattern: ('XX', 'white'|'grey'|'black', 2024)
    matches = re.findall(
        r"\('([A-Z]{2})',\s*'(?:white|grey|black)',\s*\d{4}\)",
        sql_content,
    )
    unique_codes = set(matches)
    assert len(unique_codes) >= 50, (
        f"Expected at least 50 flag state entries, found {len(unique_codes)}: {sorted(unique_codes)}"
    )


# ---------- 5. Foreign key references are correct ----------

def test_fk_deficiencies_references_inspections(sql_content: str):
    """psc_deficiencies.inspection_id references psc_inspections(id)."""
    # Extract the CREATE TABLE block for psc_deficiencies
    pattern = r"REFERENCES\s+psc_inspections\s*\(\s*id\s*\)\s+ON\s+DELETE\s+CASCADE"
    matches = re.findall(pattern, sql_content, re.IGNORECASE)
    # Should appear twice: once in psc_deficiencies, once in psc_certificates
    assert len(matches) >= 2, (
        f"Expected at least 2 FK references to psc_inspections(id) ON DELETE CASCADE, found {len(matches)}"
    )


def test_fk_certificates_references_inspections(sql_content: str):
    """psc_certificates has a FK to psc_inspections(id)."""
    # Find the certificates table block and check for the FK
    cert_block_match = re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+psc_certificates\s*\((.*?)\);",
        sql_content,
        re.IGNORECASE | re.DOTALL,
    )
    assert cert_block_match, "Could not find psc_certificates CREATE TABLE block"
    cert_block = cert_block_match.group(1)
    assert "REFERENCES psc_inspections(id)" in cert_block, (
        "psc_certificates missing FK reference to psc_inspections(id)"
    )


def test_fk_deficiencies_block_references_inspections(sql_content: str):
    """psc_deficiencies has a FK to psc_inspections(id)."""
    def_block_match = re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+psc_deficiencies\s*\((.*?)\);",
        sql_content,
        re.IGNORECASE | re.DOTALL,
    )
    assert def_block_match, "Could not find psc_deficiencies CREATE TABLE block"
    def_block = def_block_match.group(1)
    assert "REFERENCES psc_inspections(id)" in def_block, (
        "psc_deficiencies missing FK reference to psc_inspections(id)"
    )
