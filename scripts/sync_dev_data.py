#!/usr/bin/env python3
"""Sync data from prod to local dev database.

Sets up an SSH tunnel to prod, fetches vessel data (positions + profiles),
infrastructure routes, and maritime zone boundaries.

Usage:
    python3 scripts/sync_dev_data.py                       # vessels only (last 12h)
    python3 scripts/sync_dev_data.py --hours 24            # vessels, last 24h
    python3 scripts/sync_dev_data.py --all                 # everything
    python3 scripts/sync_dev_data.py --skip-vessels --with-infrastructure --with-maritime
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time

logger = logging.getLogger("sync_dev_data")

PROD_HOST = "76.13.248.226"
PROD_DB_USER = "heimdal"
PROD_DB_NAME = "heimdal"
LOCAL_DB_URL = "postgresql://heimdal:heimdal_dev@localhost:5432/heimdal"
TUNNEL_LOCAL_PORT = 15432


def wait_for_port(port: int, timeout: int = 10) -> bool:
    import socket
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return False


def sync_vessels(prod_url: str, hours: int):
    """Sync vessel profiles and positions from prod."""
    import psycopg2

    logger.info("Connecting to prod database...")
    prod_conn = psycopg2.connect(prod_url)
    prod_conn.set_session(readonly=True)
    prod_cur = prod_conn.cursor()

    # Fetch distinct MMSIs from recent positions
    logger.info("Fetching vessel MMSIs with positions in last %d hours...", hours)
    prod_cur.execute(
        "SELECT DISTINCT mmsi FROM vessel_positions WHERE timestamp > NOW() - INTERVAL '%s hours'",
        (hours,)
    )
    mmsis = [row[0] for row in prod_cur.fetchall()]
    logger.info("Found %d vessels with recent positions", len(mmsis))

    if not mmsis:
        logger.warning("No positions found in last %d hours. Nothing to sync.", hours)
        prod_cur.close()
        prod_conn.close()
        return

    # Fetch vessel_profiles
    logger.info("Fetching vessel profiles...")
    prod_cur.execute(
        "SELECT mmsi, ship_name, ship_type, imo, flag_country, "
        "last_lat, last_lon, last_position_time, "
        "risk_score, risk_tier, "
        "length, width, draught, destination, eta, "
        "registered_owner, ownership_data, network_score "
        "FROM vessel_profiles WHERE mmsi = ANY(%s)",
        (mmsis,)
    )
    profiles = prod_cur.fetchall()
    profile_cols = [desc[0] for desc in prod_cur.description]
    logger.info("Fetched %d vessel profiles", len(profiles))

    # Fetch vessel_positions
    logger.info("Fetching vessel positions (last %d hours)...", hours)
    prod_cur.execute(
        "SELECT mmsi, ST_Y(position::geometry) AS lat, ST_X(position::geometry) AS lon, "
        "sog, cog, heading, rot, nav_status, timestamp "
        "FROM vessel_positions "
        "WHERE timestamp > NOW() - INTERVAL '%s hours' "
        "ORDER BY timestamp",
        (hours,)
    )
    positions = prod_cur.fetchall()
    pos_cols = [desc[0] for desc in prod_cur.description]
    logger.info("Fetched %d positions", len(positions))

    prod_cur.close()
    prod_conn.close()

    # Insert into local dev
    logger.info("Connecting to local dev database...")
    dev_conn = psycopg2.connect(LOCAL_DB_URL)
    dev_cur = dev_conn.cursor()

    # Upsert profiles
    logger.info("Inserting vessel profiles...")
    for row in profiles:
        data = dict(zip(profile_cols, row))
        for jsonb_field in ('ownership_data',):
            if data.get(jsonb_field) and not isinstance(data[jsonb_field], str):
                data[jsonb_field] = json.dumps(data[jsonb_field])

        dev_cur.execute("""
            INSERT INTO vessel_profiles (
                mmsi, ship_name, ship_type, imo, flag_country,
                last_lat, last_lon, last_position_time,
                risk_score, risk_tier,
                length, width, draught, destination, eta,
                registered_owner, ownership_data, network_score
            ) VALUES (
                %(mmsi)s, %(ship_name)s, %(ship_type)s, %(imo)s, %(flag_country)s,
                %(last_lat)s, %(last_lon)s, %(last_position_time)s,
                %(risk_score)s, %(risk_tier)s,
                %(length)s, %(width)s, %(draught)s, %(destination)s, %(eta)s,
                %(registered_owner)s, %(ownership_data)s, %(network_score)s
            )
            ON CONFLICT (mmsi) DO UPDATE SET
                ship_name = EXCLUDED.ship_name,
                ship_type = EXCLUDED.ship_type,
                last_lat = EXCLUDED.last_lat,
                last_lon = EXCLUDED.last_lon,
                last_position_time = EXCLUDED.last_position_time,
                risk_score = EXCLUDED.risk_score,
                risk_tier = EXCLUDED.risk_tier
        """, data)

    dev_conn.commit()
    logger.info("Upserted %d vessel profiles", len(profiles))

    # Insert positions in chunks
    logger.info("Inserting positions...")
    chunk_size = 100
    commit_every = 50000
    pos_count = 0
    for i in range(0, len(positions), chunk_size):
        batch = positions[i:i + chunk_size]
        values = []
        params = []
        for j, row in enumerate(batch):
            data = dict(zip(pos_cols, row))
            prefix = f"p{j}_"
            values.append(
                f"(%({prefix}mmsi)s, "
                f"ST_MakePoint(%({prefix}lon)s, %({prefix}lat)s)::geography, "
                f"%({prefix}sog)s, %({prefix}cog)s, %({prefix}heading)s, "
                f"%({prefix}rot)s, %({prefix}nav_status)s, %({prefix}timestamp)s)"
            )
            for k, v in data.items():
                params.append((f"{prefix}{k}", v))

        dev_cur.execute(
            "INSERT INTO vessel_positions (mmsi, position, sog, cog, heading, rot, nav_status, timestamp) "
            f"VALUES {', '.join(values)} ON CONFLICT DO NOTHING",
            dict(params),
        )
        pos_count += len(batch)
        if pos_count % commit_every == 0:
            dev_conn.commit()
            logger.info("  Committed %d/%d positions...", pos_count, len(positions))

    dev_conn.commit()
    logger.info("Inserted %d positions", pos_count)

    dev_cur.close()
    dev_conn.close()
    logger.info("--- Vessels done: %d profiles, %d positions ---", len(profiles), pos_count)


def sync_infrastructure(prod_url: str):
    """Sync infrastructure_routes from prod (cables, pipelines)."""
    import psycopg2

    logger.info("Syncing infrastructure routes from prod...")
    prod_conn = psycopg2.connect(prod_url)
    prod_conn.set_session(readonly=True)
    prod_cur = prod_conn.cursor()

    prod_cur.execute(
        "SELECT id, name, route_type, operator, "
        "ST_AsText(geometry::geometry) AS geom_wkt, "
        "buffer_nm, metadata "
        "FROM infrastructure_routes"
    )
    rows = prod_cur.fetchall()
    cols = [desc[0] for desc in prod_cur.description]
    logger.info("Fetched %d infrastructure routes from prod", len(rows))

    prod_cur.close()
    prod_conn.close()

    if not rows:
        logger.info("No infrastructure routes to sync")
        return

    dev_conn = psycopg2.connect(LOCAL_DB_URL)
    dev_cur = dev_conn.cursor()

    # Clear existing and re-insert
    dev_cur.execute("DELETE FROM infrastructure_events")
    dev_cur.execute("DELETE FROM infrastructure_routes")
    dev_conn.commit()

    count = 0
    for row in rows:
        data = dict(zip(cols, row))
        if data.get("metadata") and not isinstance(data["metadata"], str):
            data["metadata"] = json.dumps(data["metadata"])

        dev_cur.execute("""
            INSERT INTO infrastructure_routes (id, name, route_type, operator, geometry, buffer_nm, metadata)
            VALUES (
                %(id)s, %(name)s, %(route_type)s, %(operator)s,
                ST_GeogFromText(%(geom_wkt)s),
                %(buffer_nm)s, %(metadata)s
            )
            ON CONFLICT (id) DO NOTHING
        """, data)
        count += 1

    dev_conn.commit()
    dev_cur.close()
    dev_conn.close()
    logger.info("--- Infrastructure done: %d routes synced ---", count)


def sync_maritime(prod_url: str):
    """Sync maritime_zones and maritime_boundaries from prod."""
    import psycopg2

    logger.info("Syncing maritime zones and boundaries from prod...")
    prod_conn = psycopg2.connect(prod_url)
    prod_conn.set_session(readonly=True)
    prod_cur = prod_conn.cursor()

    # Fetch maritime_zones
    prod_cur.execute(
        "SELECT id, zone_type, name, sovereign1, sovereign2, "
        "ST_AsText(ST_Simplify(geometry::geometry, 0.01)) AS geom_wkt "
        "FROM maritime_zones"
    )
    zones = prod_cur.fetchall()
    zone_cols = [desc[0] for desc in prod_cur.description]
    logger.info("Fetched %d maritime zones from prod", len(zones))

    # Fetch maritime_boundaries
    prod_cur.execute(
        "SELECT id, boundary_type, name, sovereign1, sovereign2, "
        "ST_AsText(ST_Simplify(geometry::geometry, 0.01)) AS geom_wkt "
        "FROM maritime_boundaries"
    )
    boundaries = prod_cur.fetchall()
    boundary_cols = [desc[0] for desc in prod_cur.description]
    logger.info("Fetched %d maritime boundaries from prod", len(boundaries))

    prod_cur.close()
    prod_conn.close()

    dev_conn = psycopg2.connect(LOCAL_DB_URL)
    dev_cur = dev_conn.cursor()

    # Clear and re-insert zones
    dev_cur.execute("DELETE FROM maritime_zones")
    dev_conn.commit()

    zone_count = 0
    for row in zones:
        data = dict(zip(zone_cols, row))
        if not data.get("geom_wkt"):
            continue
        dev_cur.execute("""
            INSERT INTO maritime_zones (id, zone_type, name, sovereign1, sovereign2, geometry)
            VALUES (%(id)s, %(zone_type)s, %(name)s, %(sovereign1)s, %(sovereign2)s,
                    ST_GeogFromText(%(geom_wkt)s))
            ON CONFLICT (id) DO NOTHING
        """, data)
        zone_count += 1

    dev_conn.commit()
    logger.info("Inserted %d maritime zones", zone_count)

    # Clear and re-insert boundaries
    dev_cur.execute("DELETE FROM maritime_boundaries")
    dev_conn.commit()

    boundary_count = 0
    for row in boundaries:
        data = dict(zip(boundary_cols, row))
        if not data.get("geom_wkt"):
            continue
        dev_cur.execute("""
            INSERT INTO maritime_boundaries (id, boundary_type, name, sovereign1, sovereign2, geometry)
            VALUES (%(id)s, %(boundary_type)s, %(name)s, %(sovereign1)s, %(sovereign2)s,
                    ST_GeogFromText(%(geom_wkt)s))
            ON CONFLICT (id) DO NOTHING
        """, data)
        boundary_count += 1

    dev_conn.commit()
    dev_cur.close()
    dev_conn.close()
    logger.info("--- Maritime done: %d zones, %d boundaries ---", zone_count, boundary_count)


def main():
    parser = argparse.ArgumentParser(description="Sync data from prod to dev")
    parser.add_argument("--hours", type=int, default=12, help="Hours of position history (default: 12)")
    parser.add_argument("--prod-host", default=PROD_HOST, help=f"Prod server IP (default: {PROD_HOST})")
    parser.add_argument("--prod-user", default="root", help="SSH user (default: root)")
    parser.add_argument("--ssh-key", default=None, help="SSH key path (default: auto)")
    parser.add_argument("--no-tunnel", action="store_true", help="Skip SSH tunnel (if already set up)")
    parser.add_argument("--with-infrastructure", action="store_true", help="Also sync infrastructure routes")
    parser.add_argument("--with-maritime", action="store_true", help="Also sync maritime zones/boundaries")
    parser.add_argument("--all", action="store_true", help="Sync everything")
    parser.add_argument("--skip-vessels", action="store_true", help="Skip vessel data")
    args = parser.parse_args()

    if args.all:
        args.with_infrastructure = True
        args.with_maritime = True

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")

    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 required: pip install psycopg2-binary")
        sys.exit(1)

    tunnel_proc = None

    try:
        # SSH tunnel
        if not args.no_tunnel:
            logger.info("Setting up SSH tunnel to %s ...", args.prod_host)
            ssh_cmd = [
                "ssh", "-N", "-L", f"{TUNNEL_LOCAL_PORT}:localhost:5432",
                f"{args.prod_user}@{args.prod_host}",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=10",
            ]
            if args.ssh_key:
                ssh_cmd.extend(["-i", args.ssh_key])

            tunnel_proc = subprocess.Popen(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if not wait_for_port(TUNNEL_LOCAL_PORT, timeout=15):
                logger.error("SSH tunnel failed to open. Check SSH access to %s", args.prod_host)
                tunnel_proc.kill()
                sys.exit(1)
            logger.info("SSH tunnel active on localhost:%d", TUNNEL_LOCAL_PORT)

        prod_port = TUNNEL_LOCAL_PORT if not args.no_tunnel else 5432
        prod_url = f"postgresql://{PROD_DB_USER}:heimdal_dev@localhost:{prod_port}/{PROD_DB_NAME}"

        if not args.skip_vessels:
            sync_vessels(prod_url, args.hours)

        if args.with_infrastructure:
            sync_infrastructure(prod_url)

        if args.with_maritime:
            sync_maritime(prod_url)

    finally:
        if tunnel_proc:
            tunnel_proc.kill()
            tunnel_proc.wait()
            logger.info("SSH tunnel closed")


if __name__ == "__main__":
    main()
