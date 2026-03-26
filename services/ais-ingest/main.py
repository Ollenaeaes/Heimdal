"""AIS ingest service entry point.

Connects to aisstream.io WebSocket, parses messages, deduplicates,
and writes positions/vessel profiles to the database in batches.

MMSI collision detection: when two different transponders broadcast the
same MMSI with different identities (ship name, call sign, IMO), the
service keeps the "trusted" identity (the one with a valid IMO) and
discards updates from the untrusted source.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

import redis.asyncio as aioredis

from shared.config import settings
from shared.logging import setup_logging
from shared.models.ais_message import PositionReport, ShipStaticData

# These imports work inside the Docker container where the service code
# lives at /app/ and sys.path includes /app/.  For the same reason,
# we import without the services.ais_ingest prefix.
from parser import parse_message, parse_vessel_extras
from dedup import Deduplicator
from metrics import MetricsPublisher
from writer import BatchWriter
from websocket import AISWebSocket

logger = logging.getLogger("ais-ingest")

# ---------------------------------------------------------------------------
# MMSI collision detection
# ---------------------------------------------------------------------------

_IDENTITY_KEY_PREFIX = "heimdal:identity"
_IDENTITY_TTL = 86400  # 24 hours

# A name is "garbled" if >30% of characters are non-alphanumeric/space
_GARBLED_RE = re.compile(r"[^A-Za-z0-9 .\-/]")


def _is_garbled_name(name: str | None) -> bool:
    """Return True if the vessel name looks garbled/corrupted."""
    if not name or len(name.strip()) == 0:
        return True
    clean = name.strip()
    bad_chars = len(_GARBLED_RE.findall(clean))
    return bad_chars / len(clean) > 0.3


async def _check_mmsi_collision(
    redis_client,
    mmsi: int,
    ship_name: str | None,
    call_sign: str | None,
    imo: int | None,
) -> bool:
    """Check if this static data conflicts with the trusted identity for this MMSI.

    Returns True if this message should be DROPPED (untrusted source).
    Returns False if this message is OK to process.

    The trusted identity is the one with a valid IMO number.
    """
    if redis_client is None:
        return False

    key = f"{_IDENTITY_KEY_PREFIX}:{mmsi}"
    stored = await redis_client.get(key)

    if stored is None:
        # First time seeing this MMSI — store as trusted identity
        identity = json.dumps({
            "ship_name": (ship_name or "").strip(),
            "call_sign": (call_sign or "").strip(),
            "imo": imo,
        })
        await redis_client.setex(key, _IDENTITY_TTL, identity)
        return False

    try:
        trusted = json.loads(stored)
    except (json.JSONDecodeError, TypeError):
        return False

    trusted_name = (trusted.get("ship_name") or "").strip().upper()
    trusted_cs = (trusted.get("call_sign") or "").strip().upper()
    trusted_imo = trusted.get("imo")

    incoming_name = (ship_name or "").strip().upper()
    incoming_cs = (call_sign or "").strip().upper()

    # Same identity — no collision
    if incoming_name == trusted_name and incoming_cs == trusted_cs:
        # Refresh TTL and update IMO if we now have one
        if imo and not trusted_imo:
            identity = json.dumps({
                "ship_name": (ship_name or "").strip(),
                "call_sign": (call_sign or "").strip(),
                "imo": imo,
            })
            await redis_client.setex(key, _IDENTITY_TTL, identity)
        return False

    # Different identity — MMSI collision detected
    # Trust the identity with a valid IMO
    if trusted_imo and not imo:
        # Trusted identity has IMO, incoming doesn't — drop incoming
        logger.warning(
            "MMSI collision detected: MMSI %d trusted=%s/%s (IMO %s), "
            "rejected=%s/%s (no IMO)",
            mmsi, trusted_name, trusted_cs, trusted_imo,
            incoming_name, incoming_cs,
        )
        return True

    if imo and not trusted_imo:
        # Incoming has IMO, trusted doesn't — replace trusted identity
        logger.warning(
            "MMSI collision: upgrading trusted identity for MMSI %d: "
            "%s/%s → %s/%s (IMO %s)",
            mmsi, trusted_name, trusted_cs,
            incoming_name, incoming_cs, imo,
        )
        identity = json.dumps({
            "ship_name": (ship_name or "").strip(),
            "call_sign": (call_sign or "").strip(),
            "imo": imo,
        })
        await redis_client.setex(key, _IDENTITY_TTL, identity)
        return False

    # Both or neither have IMO — trust the non-garbled one
    if _is_garbled_name(ship_name) and not _is_garbled_name(trusted.get("ship_name")):
        logger.warning(
            "MMSI collision: MMSI %d dropping garbled name %r (trusted: %s)",
            mmsi, ship_name, trusted_name,
        )
        return True

    # Ambiguous — keep the existing trusted identity, drop incoming
    logger.warning(
        "MMSI collision (ambiguous): MMSI %d trusted=%s, incoming=%s — keeping trusted",
        mmsi, trusted_name, incoming_name,
    )
    return True


async def main():
    setup_logging("ais-ingest")

    # Initialize Redis (optional — skip if no URL configured)
    redis = None
    dedup = None
    metrics = None
    if settings.redis_url:
        redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        dedup = Deduplicator(redis)
        metrics = MetricsPublisher(redis)

    # Convert SQLAlchemy URL to asyncpg DSN
    dsn = settings.database_url.get_secret_value().replace("+asyncpg", "")
    writer = BatchWriter(
        dsn=dsn,
        redis_client=redis,
        batch_size=settings.ingest.batch_size,
        flush_interval=settings.ingest.flush_interval,
        metrics=metrics,
    )
    await writer.start()

    msg_count = {"total": 0, "parsed": 0, "written": 0, "collision_dropped": 0}

    async def handle_message(raw: dict):
        msg_count["total"] += 1
        if msg_count["total"] % 1000 == 0:
            logger.info(
                "Messages: total=%d parsed=%d written=%d collision_dropped=%d",
                msg_count["total"], msg_count["parsed"], msg_count["written"],
                msg_count["collision_dropped"],
            )

        result = parse_message(raw)
        if result is None:
            return
        msg_count["parsed"] += 1

        if isinstance(result, ShipStaticData):
            extras = parse_vessel_extras(raw)

            # --- MMSI collision detection ---
            raw_msg = raw.get("Message", {}).get("ShipStaticData", {})
            raw_call_sign = raw_msg.get("CallSign") or None
            collision = await _check_mmsi_collision(
                redis, result.mmsi, result.ship_name, raw_call_sign, result.imo,
            )
            if collision:
                msg_count["collision_dropped"] += 1
                return

            extras["mmsi"] = result.mmsi
            if result.imo:
                extras["imo"] = result.imo
            if result.ship_name:
                extras["ship_name"] = result.ship_name
            if result.ship_type is not None:
                extras["ship_type"] = result.ship_type
            await writer.add_vessel_update(result.mmsi, extras)
            msg_count["written"] += 1

        elif isinstance(result, PositionReport):
            if dedup and await dedup.is_duplicate(result.mmsi, result.timestamp):
                return
            await writer.add_position(result)
            msg_count["written"] += 1

    ws = AISWebSocket(on_message=handle_message)

    try:
        await ws.start()
    except KeyboardInterrupt:
        pass
    finally:
        await ws.stop()
        await writer.stop()
        if redis:
            await redis.close()


if __name__ == "__main__":
    asyncio.run(main())
