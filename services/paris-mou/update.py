#!/usr/bin/env python3
"""Incremental Paris MoU data update service.

Runs weekly to fetch and ingest new inspection files from the Paris MoU DES API.
Tracks processed files in the psc_download_log table to avoid re-processing.

Designed to run as a scheduled batch job — not an always-on container.

Docker Compose (add under batch profile):
    paris-mou-update:
      build:
        context: .
        dockerfile: services/paris-mou/Dockerfile
      env_file: .env
      profiles: ["batch"]
      depends_on:
        postgres:
          condition: service_healthy

Cron entry (weekly, Sundays at 03:00):
    0 3 * * 0 cd /path/to/heimdal && docker compose run --rm paris-mou-update
"""

import json
import logging
import os
import re
import sys
import tempfile
import time
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv

# Add project root to path so we can import shared modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.parsers.paris_mou import parse_paris_mou_xml

logger = logging.getLogger("paris-mou-update")

BASE_URL = "https://fileserver.parismou.org/api"

# ---------------------------------------------------------------------------
# Download tracking table
# ---------------------------------------------------------------------------

CREATE_DOWNLOAD_LOG_SQL = """
CREATE TABLE IF NOT EXISTS psc_download_log (
    filename VARCHAR(255) PRIMARY KEY,
    downloaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    record_count INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'completed'
);
"""


def ensure_tracking_table(conn):
    """Create the psc_download_log table if it doesn't exist."""
    with conn.cursor() as cur:
        cur.execute(CREATE_DOWNLOAD_LOG_SQL)
    conn.commit()
    logger.info("Ensured psc_download_log table exists.")


def get_processed_files(conn) -> set[str]:
    """Return set of filenames already successfully processed."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT filename FROM psc_download_log WHERE status = 'completed'"
        )
        return {row[0] for row in cur.fetchall()}


def record_download(conn, filename: str, record_count: int, status: str = "completed"):
    """Record a processed file in the download log."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO psc_download_log (filename, record_count, status)
            VALUES (%s, %s, %s)
            ON CONFLICT (filename) DO UPDATE
                SET downloaded_at = NOW(),
                    record_count = EXCLUDED.record_count,
                    status = EXCLUDED.status
            """,
            (filename, record_count, status),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# API helpers (reused patterns from scripts/ingest_paris_mou.py)
# ---------------------------------------------------------------------------

def parse_response(text):
    """Parse response -- try JSON first, fall back to reading PHP print_r output."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    result = {}
    code_match = re.search(r'\[code\]\s*=>\s*(\S+)', text)
    msg_match = re.search(r'\[message\]\s*=>\s*(.+)', text)
    token_match = re.search(r'\[access_token\]\s*=>\s*(\S+)', text)
    ip_match = re.search(r'\[source_ip\]\s*=>\s*(\S+)', text)

    result["status"] = {
        "code": code_match.group(1) if code_match else "unknown",
        "message": msg_match.group(1).strip() if msg_match else "unknown",
    }
    if token_match:
        result["access_token"] = token_match.group(1)
    if ip_match:
        result["source_ip"] = ip_match.group(1)

    # Extract files array if present
    files_match = re.findall(r'\[\d+\]\s*=>\s*(.+)', text)
    if files_match:
        result["files"] = [f.strip() for f in files_match]

    return result


def get_auth_token(api_key: str, retry: bool = True) -> str:
    """Exchange API key for a short-lived authorization token.

    Retries once after 30s on failure (Paris MoU server can be flaky).
    """
    url = f"{BASE_URL}/{api_key}/getauthorizationtoken"
    logger.info("Authenticating with Paris MoU DES API...")

    try:
        resp = requests.get(url, timeout=30)
        data = parse_response(resp.text)

        if data.get("status", {}).get("code") != "success":
            raise RuntimeError(
                f"Auth failed: {data.get('status', {}).get('message', 'unknown error')}"
            )

        token = data["access_token"]
        logger.info("Authorization token obtained.")
        return token

    except Exception as exc:
        if retry:
            logger.warning("Auth failed (%s), retrying in 30s...", exc)
            time.sleep(30)
            return get_auth_token(api_key, retry=False)
        raise SystemExit(f"Auth failed after retry: {exc}") from exc


def get_file_list(token: str) -> list[str]:
    """List available GetPublicFile_* files on the DES server."""
    url = f"{BASE_URL}/{token}/getfilelist"
    logger.info("Fetching file list from DES API...")
    resp = requests.get(url, timeout=30)
    data = parse_response(resp.text)

    if data.get("status", {}).get("code") != "success":
        raise SystemExit(f"getfilelist failed: {json.dumps(data, indent=2)}")

    raw_files = data.get("files", [])
    all_files = [f for f in raw_files if f and not f.strip().isdigit()]
    inspection_files = [f for f in all_files if re.match(r"GetPublicFile_", f)]

    logger.info(
        "Found %d inspection files out of %d total files on server.",
        len(inspection_files),
        len(all_files),
    )
    return inspection_files


def download_file(token: str, filename: str, dest_dir: Path) -> Path:
    """Download a single file from the DES API."""
    url = f"{BASE_URL}/{token}/getfile/{filename}"
    logger.info("Downloading %s ...", filename)
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()

    out_path = dest_dir / filename
    out_path.write_bytes(resp.content)
    size_kb = len(resp.content) / 1024
    logger.info("Saved %s (%.1f KB)", out_path, size_kb)
    return out_path


# ---------------------------------------------------------------------------
# Database insert (same logic as scripts/ingest_paris_mou.py)
# ---------------------------------------------------------------------------

INSPECTION_SQL = """
    INSERT INTO psc_inspections (
        inspection_id, imo, ship_name, flag_state, ship_type, gross_tonnage,
        keel_laid_date, inspection_date, inspection_end_date, inspection_type,
        inspection_port, port_country, reporting_authority, detained,
        deficiency_count, ism_deficiency, ro_at_inspection,
        pi_provider_at_inspection, pi_is_ig_member,
        ism_company_imo, ism_company_name, raw_data
    ) VALUES (
        %(inspection_id)s, %(imo)s, %(ship_name)s, %(flag_state)s, %(ship_type)s,
        %(gross_tonnage)s, %(keel_laid_date)s, %(inspection_date)s,
        %(inspection_end_date)s, %(inspection_type)s, %(inspection_port)s,
        %(port_country)s, %(reporting_authority)s, %(detained)s,
        %(deficiency_count)s, %(ism_deficiency)s, %(ro_at_inspection)s,
        %(pi_provider_at_inspection)s, %(pi_is_ig_member)s,
        %(ism_company_imo)s, %(ism_company_name)s, %(raw_data)s
    )
    ON CONFLICT (inspection_id) DO NOTHING
    RETURNING id
"""

DEFICIENCY_SQL = """
    INSERT INTO psc_deficiencies (
        inspection_id, deficiency_code, nature_of_defect,
        is_ground_detention, is_ro_related, is_accidental_damage
    ) VALUES (%(inspection_id)s, %(deficiency_code)s, %(nature_of_defect)s,
              %(is_ground_detention)s, %(is_ro_related)s, %(is_accidental_damage)s)
"""

CERTIFICATE_SQL = """
    INSERT INTO psc_certificates (
        inspection_id, certificate_type, issuing_authority,
        issuing_authority_type, expiry_date, issue_date, certificate_source
    ) VALUES (%(inspection_id)s, %(certificate_type)s, %(issuing_authority)s,
              %(issuing_authority_type)s, %(expiry_date)s, %(issue_date)s,
              %(certificate_source)s)
"""


def insert_inspections(conn, inspections: list[dict]) -> dict:
    """Insert parsed inspections into the database.

    Returns dict with counts: inserted, skipped, deficiencies, certificates.
    """
    stats = {"inserted": 0, "skipped": 0, "deficiencies": 0, "certificates": 0}
    cur = conn.cursor()

    for record in inspections:
        try:
            if not record.get("imo") or not record.get("inspection_date"):
                logger.warning(
                    "Skipping inspection %s: missing imo or inspection_date",
                    record.get("inspection_id"),
                )
                stats["skipped"] += 1
                continue

            row = {
                "inspection_id": record["inspection_id"],
                "imo": record["imo"],
                "ship_name": record.get("ship_name"),
                "flag_state": record.get("flag_state"),
                "ship_type": record.get("ship_type"),
                "gross_tonnage": record.get("gross_tonnage"),
                "keel_laid_date": record.get("keel_laid_date"),
                "inspection_date": record["inspection_date"],
                "inspection_end_date": record.get("inspection_end_date"),
                "inspection_type": record.get("inspection_type"),
                "inspection_port": record.get("inspection_port"),
                "port_country": record.get("port_country"),
                "reporting_authority": record.get("reporting_authority"),
                "detained": record.get("detained", False),
                "deficiency_count": record.get("deficiency_count", 0),
                "ism_deficiency": record.get("ism_deficiency", False),
                "ro_at_inspection": record.get("ro_at_inspection"),
                "pi_provider_at_inspection": record.get("pi_provider_at_inspection"),
                "pi_is_ig_member": record.get("pi_is_ig_member"),
                "ism_company_imo": record.get("ism_company_imo"),
                "ism_company_name": record.get("ism_company_name"),
                "raw_data": json.dumps(record.get("raw_data", {})),
            }

            cur.execute(INSPECTION_SQL, row)
            result = cur.fetchone()

            if result is None:
                stats["skipped"] += 1
                continue

            db_id = result[0]
            stats["inserted"] += 1

            for deficiency in record.get("deficiencies", []):
                deficiency["inspection_id"] = db_id
                cur.execute(DEFICIENCY_SQL, deficiency)
                stats["deficiencies"] += 1

            for cert in record.get("certificates", []):
                cert["inspection_id"] = db_id
                cur.execute(CERTIFICATE_SQL, cert)
                stats["certificates"] += 1

        except Exception:
            logger.exception(
                "Error inserting inspection %s", record.get("inspection_id")
            )
            stats["skipped"] += 1
            continue

    cur.close()
    return stats


# ---------------------------------------------------------------------------
# File processing
# ---------------------------------------------------------------------------

def process_file(filepath: Path, conn) -> dict:
    """Parse an XML file and insert inspections into DB. Returns stats dict."""
    logger.info("Processing %s ...", filepath.name)
    t0 = time.time()

    inspections = list(parse_paris_mou_xml(str(filepath)))
    elapsed_parse = time.time() - t0
    logger.info(
        "Parsed %d inspections from %s in %.1fs",
        len(inspections),
        filepath.name,
        elapsed_parse,
    )

    # Insert in chunks of 1000 to avoid holding too much in memory
    total_stats = {"inserted": 0, "skipped": 0, "deficiencies": 0, "certificates": 0}
    chunk_size = 1000

    for i in range(0, len(inspections), chunk_size):
        chunk = inspections[i : i + chunk_size]
        chunk_stats = insert_inspections(conn, chunk)
        for key in total_stats:
            total_stats[key] += chunk_stats[key]

    conn.commit()
    elapsed_total = time.time() - t0
    logger.info(
        "File %s: inserted=%d, skipped=%d, deficiencies=%d, certificates=%d (%.1fs)",
        filepath.name,
        total_stats["inserted"],
        total_stats["skipped"],
        total_stats["deficiencies"],
        total_stats["certificates"],
        elapsed_total,
    )
    return total_stats


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def setup_logging_for_service():
    """Configure logging — use shared JSON logging if available, else text."""
    try:
        from shared.logging import setup_logging
        setup_logging("paris-mou-update")
    except ImportError:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            datefmt="%H:%M:%S",
        )


def main():
    load_dotenv()
    setup_logging_for_service()

    # Validate required env vars
    api_key = os.environ.get("PARIS_MOU_KEY")
    if not api_key:
        logger.error("PARIS_MOU_KEY not set in environment.")
        sys.exit(1)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL not set in environment.")
        sys.exit(1)

    t_start = time.time()

    # Connect to DB and ensure tracking table exists
    conn = psycopg2.connect(db_url)
    try:
        ensure_tracking_table(conn)
        already_processed = get_processed_files(conn)
        logger.info("Found %d previously processed files.", len(already_processed))

        # Authenticate and get file list
        token = get_auth_token(api_key)
        remote_files = get_file_list(token)

        if not remote_files:
            logger.info("No inspection files found on server.")
            return

        # Determine new files
        new_files = [f for f in remote_files if f not in already_processed]
        new_files.sort()  # Process oldest first

        if not new_files:
            logger.info("No new files to process. All %d files already ingested.", len(remote_files))
            return

        logger.info(
            "%d new files to process (out of %d on server).",
            len(new_files),
            len(remote_files),
        )

        # Download and ingest each new file using a temp directory
        grand_total = {"inserted": 0, "skipped": 0, "deficiencies": 0, "certificates": 0}
        files_processed = 0
        files_failed = 0

        with tempfile.TemporaryDirectory(prefix="paris-mou-") as tmpdir:
            tmpdir_path = Path(tmpdir)

            for filename in new_files:
                try:
                    # Download
                    filepath = download_file(token, filename, tmpdir_path)

                    # Ingest
                    stats = process_file(filepath, conn)

                    # Record success
                    record_count = stats["inserted"] + stats["skipped"]
                    record_download(conn, filename, record_count, "completed")

                    for key in grand_total:
                        grand_total[key] += stats[key]
                    files_processed += 1

                    # Clean up temp file immediately to save disk space
                    filepath.unlink(missing_ok=True)

                except Exception:
                    logger.exception("Failed to process %s, skipping.", filename)
                    try:
                        record_download(conn, filename, 0, "failed")
                    except Exception:
                        logger.exception("Failed to record error for %s.", filename)
                    conn.rollback()
                    files_failed += 1

        elapsed = time.time() - t_start
        logger.info(
            "Update complete in %.1fs: %d files processed, %d failed. "
            "Inserted %d inspections, %d deficiencies, %d certificates.",
            elapsed,
            files_processed,
            files_failed,
            grand_total["inserted"],
            grand_total["deficiencies"],
            grand_total["certificates"],
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
