#!/usr/bin/env python3
"""
Historical batch ingest for Paris MoU PSC inspection data.

Downloads XML files from the Paris MoU DES API and ingests them into
the psc_inspections, psc_deficiencies, and psc_certificates tables.

Usage:
    python3 scripts/ingest_paris_mou.py [options]

Options:
    --dry-run         List available files and estimated record counts without writing to DB
    --file FILE       Process a specific local file instead of downloading
    --download-only   Download files but don't ingest
    --db-url URL      Database URL (default from DATABASE_URL env var)
    --data-dir DIR    Directory for downloaded files (default: data/paris_mou/)
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Add project root to path so we can import shared modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.parsers.paris_mou import parse_paris_mou_xml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_URL = "https://fileserver.parismou.org/api"


# ---------------------------------------------------------------------------
# API helpers (reused from test_paris_mou.py)
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


def get_auth_token(api_key: str) -> str:
    """Exchange API key for a short-lived authorization token."""
    url = f"{BASE_URL}/{api_key}/getauthorizationtoken"
    logger.info("Authenticating with Paris MoU DES API...")
    resp = requests.get(url, timeout=30)
    data = parse_response(resp.text)

    if data.get("status", {}).get("code") != "success":
        ip = data.get("source_ip", "unknown")
        msg = data.get("status", {}).get("message", "unknown error")
        raise SystemExit(
            f"Auth failed: {msg}\nYour IP: {ip}\n"
            "You may need to whitelist this IP with Paris MoU."
        )

    token = data["access_token"]
    logger.info("Authorization token obtained.")
    return token


def get_file_list(token: str) -> list[str]:
    """List available files on the DES server, filtered to GetPublicFile_* pattern."""
    url = f"{BASE_URL}/{token}/getfilelist"
    logger.info("Fetching file list from DES API...")
    resp = requests.get(url, timeout=30)
    data = parse_response(resp.text)

    if data.get("status", {}).get("code") != "success":
        raise SystemExit(f"getfilelist failed: {json.dumps(data, indent=2)}")

    raw_files = data.get("files", [])
    # Filter out size entries ("0") and empty strings
    all_files = [f for f in raw_files if f and not f.strip().isdigit()]
    # Keep only GetPublicFile_* (inspection data)
    inspection_files = filter_inspection_files(all_files)
    logger.info(
        "Found %d inspection files out of %d total files on server.",
        len(inspection_files),
        len(all_files),
    )
    return inspection_files


def filter_inspection_files(files: list[str]) -> list[str]:
    """Filter file list to only GetPublicFile_* inspection data files."""
    return [f for f in files if re.match(r"GetPublicFile_", f)]


def download_file(token: str, filename: str, data_dir: Path) -> Path:
    """Download a single file from the DES API. Returns path to the local file."""
    url = f"{BASE_URL}/{token}/getfile/{filename}"
    logger.info("Downloading %s ...", filename)
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()

    out_path = data_dir / filename
    out_path.write_bytes(resp.content)
    size_kb = len(resp.content) / 1024
    logger.info("Saved %s (%.1f KB)", out_path, size_kb)
    return out_path


# ---------------------------------------------------------------------------
# Database insert
# ---------------------------------------------------------------------------

def insert_inspections_batch(conn, inspections: list[dict]) -> dict:
    """Insert a batch of parsed inspections into the database.

    Returns dict with counts: inserted, skipped, deficiencies, certificates.
    """
    stats = {"inserted": 0, "skipped": 0, "deficiencies": 0, "certificates": 0}

    inspection_sql = """
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

    deficiency_sql = """
        INSERT INTO psc_deficiencies (
            inspection_id, deficiency_code, nature_of_defect,
            is_ground_detention, is_ro_related, is_accidental_damage
        ) VALUES (%(inspection_id)s, %(deficiency_code)s, %(nature_of_defect)s,
                  %(is_ground_detention)s, %(is_ro_related)s, %(is_accidental_damage)s)
    """

    certificate_sql = """
        INSERT INTO psc_certificates (
            inspection_id, certificate_type, issuing_authority,
            issuing_authority_type, expiry_date, issue_date, certificate_source
        ) VALUES (%(inspection_id)s, %(certificate_type)s, %(issuing_authority)s,
                  %(issuing_authority_type)s, %(expiry_date)s, %(issue_date)s,
                  %(certificate_source)s)
    """

    cur = conn.cursor()

    for record in inspections:
        try:
            # Skip records without required fields
            if not record.get("imo") or not record.get("inspection_date"):
                logger.warning(
                    "Skipping inspection %s: missing imo or inspection_date",
                    record.get("inspection_id"),
                )
                stats["skipped"] += 1
                continue

            # Prepare inspection row
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

            cur.execute(inspection_sql, row)
            result = cur.fetchone()

            if result is None:
                # ON CONFLICT DO NOTHING — duplicate
                stats["skipped"] += 1
                continue

            db_id = result[0]
            stats["inserted"] += 1

            # Insert deficiencies
            for deficiency in record.get("deficiencies", []):
                deficiency["inspection_id"] = db_id
                cur.execute(deficiency_sql, deficiency)
                stats["deficiencies"] += 1

            # Insert certificates
            for cert in record.get("certificates", []):
                cert["inspection_id"] = db_id
                cur.execute(certificate_sql, cert)
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
# Main workflow
# ---------------------------------------------------------------------------

def process_file(filepath: Path, conn=None, dry_run: bool = False) -> dict:
    """Parse a single file and optionally insert into DB.

    Returns dict with counts.
    """
    logger.info("Processing %s ...", filepath.name)
    t0 = time.time()

    inspections = []
    deficiency_file_count = 0

    for record in parse_paris_mou_xml(str(filepath)):
        inspections.append(record)
        if record.get("deficiency_count", 0) > 0:
            deficiency_file_count += 1

    elapsed = time.time() - t0
    logger.info(
        "Parsed %d inspections (%d with deficiencies) from %s in %.1fs",
        len(inspections),
        deficiency_file_count,
        filepath.name,
        elapsed,
    )

    if dry_run:
        return {
            "file": filepath.name,
            "inspections": len(inspections),
            "with_deficiencies": deficiency_file_count,
        }

    if conn is None:
        raise RuntimeError("No database connection provided and not in dry-run mode")

    # Insert in chunks of 1000
    total_stats = {"inserted": 0, "skipped": 0, "deficiencies": 0, "certificates": 0}
    chunk_size = 1000

    for i in range(0, len(inspections), chunk_size):
        chunk = inspections[i : i + chunk_size]
        chunk_stats = insert_inspections_batch(conn, chunk)
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


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Ingest Paris MoU PSC inspection data into the database."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List available files and estimated record counts without writing to DB",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Process a specific local file instead of downloading",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Download files but don't ingest",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Database URL (default from DATABASE_URL env var)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Directory for downloaded files (default: data/paris_mou/)",
    )
    return parser


def main():
    load_dotenv()

    parser = build_arg_parser()
    args = parser.parse_args()

    # Resolve data directory
    data_dir = Path(args.data_dir) if args.data_dir else PROJECT_ROOT / "data" / "paris_mou"
    data_dir.mkdir(parents=True, exist_ok=True)

    t_start = time.time()

    # --file mode: process a single local file
    if args.file:
        filepath = Path(args.file)
        if not filepath.exists():
            raise SystemExit(f"File not found: {filepath}")

        if args.dry_run:
            result = process_file(filepath, dry_run=True)
            print(f"\n{'='*60}")
            print(f"DRY RUN — {result['file']}")
            print(f"  Inspections: {result['inspections']}")
            print(f"  With deficiencies: {result['with_deficiencies']}")
            return

        # Connect to DB and process
        import psycopg2
        db_url = args.db_url or os.environ.get("DATABASE_URL")
        if not db_url:
            raise SystemExit("DATABASE_URL not set. Use --db-url or set DATABASE_URL env var.")
        conn = psycopg2.connect(db_url)
        try:
            process_file(filepath, conn=conn)
        finally:
            conn.close()
        return

    # API mode: authenticate and list/download files
    api_key = os.environ.get("PARIS_MOU_KEY")
    if not api_key:
        raise SystemExit("PARIS_MOU_KEY not found in environment. Set it in .env")

    token = get_auth_token(api_key)
    remote_files = get_file_list(token)

    if not remote_files:
        logger.warning("No GetPublicFile_* files found on server.")
        return

    # Sort by filename (which includes date) — newest first
    remote_files.sort(reverse=True)

    # Check which files we already have locally
    existing = {f.name for f in data_dir.iterdir() if f.is_file()}
    new_files = [f for f in remote_files if f not in existing]
    logger.info(
        "%d files on server, %d already downloaded, %d new.",
        len(remote_files),
        len(remote_files) - len(new_files),
        len(new_files),
    )

    # Download new files
    downloaded_paths = []
    for filename in new_files:
        try:
            path = download_file(token, filename, data_dir)
            downloaded_paths.append(path)
        except Exception:
            logger.exception("Failed to download %s, skipping.", filename)

    if args.download_only:
        logger.info("Download-only mode: downloaded %d files.", len(downloaded_paths))
        return

    # Build list of all files to process (newest first)
    all_local_files = sorted(data_dir.iterdir(), reverse=True)
    inspection_files = [
        f for f in all_local_files
        if f.is_file() and re.match(r"GetPublicFile_", f.name)
    ]

    if args.dry_run:
        print(f"\n{'='*60}")
        print("DRY RUN — File summary:")
        print(f"{'='*60}")
        total_inspections = 0
        total_with_defs = 0
        for filepath in inspection_files:
            result = process_file(filepath, dry_run=True)
            total_inspections += result["inspections"]
            total_with_defs += result["with_deficiencies"]
            print(
                f"  {result['file']}: "
                f"{result['inspections']} inspections, "
                f"{result['with_deficiencies']} with deficiencies"
            )
        print(f"\nTotal: {total_inspections} inspections, {total_with_defs} with deficiencies")
        return

    # Connect to DB and ingest
    import psycopg2
    db_url = args.db_url or os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL not set. Use --db-url or set DATABASE_URL env var.")

    conn = psycopg2.connect(db_url)
    grand_total = {"inserted": 0, "skipped": 0, "deficiencies": 0, "certificates": 0}

    try:
        for filepath in inspection_files:
            try:
                stats = process_file(filepath, conn=conn)
                for key in grand_total:
                    grand_total[key] += stats[key]
            except Exception:
                logger.exception("Error processing %s, skipping.", filepath.name)
                conn.rollback()
    finally:
        conn.close()

    elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"Ingest complete in {elapsed:.1f}s")
    print(f"  Files processed: {len(inspection_files)}")
    print(f"  Inspections inserted: {grand_total['inserted']}")
    print(f"  Inspections skipped (duplicates): {grand_total['skipped']}")
    print(f"  Deficiencies inserted: {grand_total['deficiencies']}")
    print(f"  Certificates inserted: {grand_total['certificates']}")


if __name__ == "__main__":
    main()
