"""WebSocket alert streaming endpoint.

Provides:
- WS /ws/alerts — streams risk_change and anomaly events from Redis
  pub/sub to all connected WebSocket clients (no client-side filtering)

Clients connect and receive all risk_change and anomaly events.  Each event
includes a ``type`` field ("risk_change" or "anomaly") plus the original
event payload (mmsi, vessel_name, and event-specific fields).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger("api-server.ws_alerts")

router = APIRouter(tags=["alerts"])

# Redis channel names
RISK_CHANGES_CHANNEL = "heimdal:risk_changes"
ANOMALIES_CHANNEL = "heimdal:anomalies"

# Map channel name to alert type
_CHANNEL_TO_TYPE = {
    RISK_CHANGES_CHANNEL: "risk_change",
    ANOMALIES_CHANNEL: "anomaly",
}


class AlertConnectionManager:
    """Manages WebSocket connections for alert streaming."""

    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()

    async def add(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        logger.info("Alert client connected (%d total)", len(self._connections))

    def remove(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)
        logger.info("Alert client disconnected (%d total)", len(self._connections))

    async def broadcast(self, message: dict) -> None:
        """Send a message to all connected clients.

        Silently removes clients that have disconnected.
        """
        payload = json.dumps(message)
        disconnected: list[WebSocket] = []
        for ws in self._connections:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(payload)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self._connections.discard(ws)

    @property
    def active_connections(self) -> int:
        return len(self._connections)


manager = AlertConnectionManager()


async def _listen_redis(app_state: Any) -> None:
    """Subscribe to Redis channels and broadcast messages to WebSocket clients."""
    redis = app_state.redis
    pubsub = redis.pubsub()
    await pubsub.subscribe(RISK_CHANGES_CHANNEL, ANOMALIES_CHANNEL)
    logger.info(
        "Subscribed to Redis channels: %s, %s",
        RISK_CHANGES_CHANNEL,
        ANOMALIES_CHANNEL,
    )

    try:
        async for raw_message in pubsub.listen():
            if raw_message["type"] != "message":
                continue

            channel = raw_message["channel"]
            alert_type = _CHANNEL_TO_TYPE.get(channel)
            if alert_type is None:
                continue

            try:
                data = json.loads(raw_message["data"])
            except (json.JSONDecodeError, TypeError):
                logger.warning("Invalid JSON on channel %s: %s", channel, raw_message["data"])
                continue

            data["type"] = alert_type
            await manager.broadcast(data)
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(RISK_CHANGES_CHANNEL, ANOMALIES_CHANNEL)
        await pubsub.close()
        logger.info("Unsubscribed from Redis channels")


# Track the background Redis listener task
_redis_listener_task: asyncio.Task | None = None


def _ensure_redis_listener(app_state: Any) -> None:
    """Start the Redis listener task if not already running."""
    global _redis_listener_task
    if _redis_listener_task is None or _redis_listener_task.done():
        _redis_listener_task = asyncio.create_task(_listen_redis(app_state))


@router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket) -> None:
    """WebSocket endpoint that streams alert events to connected clients."""
    _ensure_redis_listener(websocket.app.state)

    await manager.add(websocket)
    try:
        while True:
            # Keep connection alive — no client messages expected,
            # but receive_text() will raise WebSocketDisconnect on close
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.remove(websocket)
