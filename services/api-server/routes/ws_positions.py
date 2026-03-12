"""WebSocket position streaming endpoint for the Heimdal API server.

Provides:
- WS /ws/positions — real-time vessel position streaming with per-client filters

Clients connect and optionally send a JSON subscription filter:
    {
        "bbox": [sw_lat, sw_lon, ne_lat, ne_lon],
        "risk_tiers": ["red", "yellow"],
        "ship_types": [70, 80],
        "mmsi_list": [211000001, 211000002]
    }

Positions arrive via Redis pub/sub on channel ``heimdal:positions`` and are
forwarded to each connected client whose subscription filter matches.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("api-server.ws_positions")

router = APIRouter()

REDIS_CHANNEL = "heimdal:positions"


@dataclass
class Subscription:
    """Per-client subscription filter."""

    bbox: list[float] | None = None  # [sw_lat, sw_lon, ne_lat, ne_lon]
    risk_tiers: list[str] | None = None
    ship_types: list[int] | None = None
    mmsi_list: list[int] | None = None


@dataclass
class ClientConnection:
    """A connected WebSocket client and its subscription."""

    websocket: WebSocket
    subscription: Subscription = field(default_factory=Subscription)


def matches_filter(position: dict[str, Any], sub: Subscription) -> bool:
    """Check whether a position message matches the client's subscription.

    Each filter field is optional.  When a field is ``None`` (not set),
    it passes all messages for that dimension.  A position must pass
    ALL active filters.
    """
    # bbox filter
    if sub.bbox is not None:
        sw_lat, sw_lon, ne_lat, ne_lon = sub.bbox
        lat = position.get("lat")
        lon = position.get("lon")
        if lat is None or lon is None:
            return False
        if not (sw_lat <= lat <= ne_lat and sw_lon <= lon <= ne_lon):
            return False

    # risk_tiers filter
    if sub.risk_tiers is not None:
        if position.get("risk_tier") not in sub.risk_tiers:
            return False

    # ship_types filter
    if sub.ship_types is not None:
        if position.get("ship_type") not in sub.ship_types:
            return False

    # mmsi_list filter
    if sub.mmsi_list is not None:
        if position.get("mmsi") not in sub.mmsi_list:
            return False

    return True


def _parse_subscription(data: dict[str, Any]) -> Subscription:
    """Parse a subscription filter message from the client."""
    sub = Subscription()

    bbox = data.get("bbox")
    if bbox is not None:
        if isinstance(bbox, list) and len(bbox) == 4:
            try:
                sub.bbox = [float(v) for v in bbox]
            except (TypeError, ValueError):
                pass

    risk_tiers = data.get("risk_tiers")
    if risk_tiers is not None and isinstance(risk_tiers, list):
        sub.risk_tiers = [str(t) for t in risk_tiers]

    ship_types = data.get("ship_types")
    if ship_types is not None and isinstance(ship_types, list):
        try:
            sub.ship_types = [int(t) for t in ship_types]
        except (TypeError, ValueError):
            pass

    mmsi_list = data.get("mmsi_list")
    if mmsi_list is not None and isinstance(mmsi_list, list):
        try:
            sub.mmsi_list = [int(m) for m in mmsi_list]
        except (TypeError, ValueError):
            pass

    return sub


class PositionConnectionManager:
    """Manages WebSocket clients and distributes Redis pub/sub messages."""

    def __init__(self) -> None:
        self.clients: list[ClientConnection] = []

    async def connect(self, websocket: WebSocket) -> ClientConnection:
        await websocket.accept()
        client = ClientConnection(websocket=websocket)
        self.clients.append(client)
        logger.info("Client connected, total clients: %d", len(self.clients))
        return client

    def disconnect(self, client: ClientConnection) -> None:
        if client in self.clients:
            self.clients.remove(client)
        logger.info("Client disconnected, total clients: %d", len(self.clients))

    async def broadcast_position(self, position: dict[str, Any]) -> None:
        """Send a position update to all clients whose filter matches."""
        # Extract the fields we forward to clients
        message = {
            "mmsi": position.get("mmsi"),
            "lat": position.get("lat"),
            "lon": position.get("lon"),
            "sog": position.get("sog"),
            "cog": position.get("cog"),
            "risk_tier": position.get("risk_tier"),
            "risk_score": position.get("risk_score"),
            "timestamp": position.get("timestamp"),
        }
        payload = json.dumps(message)

        disconnected: list[ClientConnection] = []
        for client in self.clients:
            if matches_filter(position, client.subscription):
                try:
                    await client.websocket.send_text(payload)
                except Exception:
                    disconnected.append(client)

        for client in disconnected:
            self.disconnect(client)


manager = PositionConnectionManager()


async def _listen_redis(app_state: Any) -> None:
    """Subscribe to Redis channel and broadcast positions to clients."""
    redis = app_state.redis
    pubsub = redis.pubsub()
    await pubsub.subscribe(REDIS_CHANNEL)
    logger.info("Subscribed to Redis channel: %s", REDIS_CHANNEL)

    try:
        async for raw_message in pubsub.listen():
            if raw_message["type"] != "message":
                continue
            try:
                position = json.loads(raw_message["data"])
            except (json.JSONDecodeError, TypeError):
                logger.warning("Invalid JSON on Redis channel")
                continue
            await manager.broadcast_position(position)
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(REDIS_CHANNEL)
        await pubsub.close()
        logger.info("Unsubscribed from Redis channel: %s", REDIS_CHANNEL)


# Track the background Redis listener task
_redis_listener_task: asyncio.Task | None = None


def _ensure_redis_listener(app_state: Any) -> None:
    """Start the Redis listener task if not already running."""
    global _redis_listener_task
    if _redis_listener_task is None or _redis_listener_task.done():
        _redis_listener_task = asyncio.create_task(_listen_redis(app_state))


@router.websocket("/ws/positions")
async def websocket_positions(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time vessel position streaming."""
    _ensure_redis_listener(websocket.app.state)

    client = await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                parsed = json.loads(data)
                client.subscription = _parse_subscription(parsed)
                logger.info(
                    "Client updated subscription: %s", client.subscription
                )
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"error": "Invalid JSON"})
                )
    except WebSocketDisconnect:
        manager.disconnect(client)
