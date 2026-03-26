"""Persistent auto-reconnecting WebSocket client for aisstream.io.

Handles exponential backoff on connection failures and detects stale
connections (no messages received within the configured timeout).
"""

from __future__ import annotations

import asyncio
import logging
import time

try:
    import orjson

    def _json_loads(data):
        return orjson.loads(data)

    def _json_dumps(obj):
        return orjson.dumps(obj).decode("utf-8")

except ImportError:
    import json

    _json_loads = json.loads
    _json_dumps = json.dumps

import websockets

from shared.config import settings

logger = logging.getLogger("ais-ingest")


class AISWebSocket:
    """Persistent auto-reconnecting WebSocket to aisstream.io."""

    WS_URL = "wss://stream.aisstream.io/v0/stream"

    def __init__(self, on_message, api_key: str | None = None):
        self.on_message = on_message  # async callback for each parsed message
        self.api_key = api_key or settings.aisstream_api_key
        self._initial_delay = 1.0
        self._max_delay = settings.ingest.reconnect_max
        self._backoff_factor = 2
        self._stale_timeout = settings.ingest.stale_connection
        self._current_delay = self._initial_delay
        self._state = "disconnected"
        self._running = False
        self._last_message_time = 0.0

    async def start(self):
        """Start the WebSocket connection loop."""
        self._running = True
        while self._running:
            try:
                self._set_state("connecting")
                async with websockets.connect(self.WS_URL) as ws:
                    self._set_state("connected")
                    self._current_delay = self._initial_delay  # reset backoff

                    # Send subscription
                    await ws.send(_json_dumps(self._subscription_message()))

                    # Receive loop with stale detection
                    while self._running:
                        try:
                            raw = await asyncio.wait_for(
                                ws.recv(), timeout=self._stale_timeout
                            )
                        except asyncio.TimeoutError:
                            logger.warning(
                                "Stale connection detected (no message for %.0fs),"
                                " forcing reconnect",
                                self._stale_timeout,
                            )
                            break

                        self._last_message_time = time.time()
                        try:
                            msg = _json_loads(raw)
                            await self.on_message(msg)
                        except Exception:
                            # Don't let message processing errors kill the
                            # WebSocket connection — log and continue
                            logger.exception("Error processing message")

            except (websockets.ConnectionClosed, OSError, ConnectionRefusedError) as e:
                self._set_state("disconnected")
                logger.warning(
                    "Connection lost: %s. Reconnecting in %.1fs",
                    e,
                    self._current_delay,
                )
                await asyncio.sleep(self._current_delay)
                self._current_delay = min(
                    self._current_delay * self._backoff_factor, self._max_delay
                )
                self._set_state("reconnecting")
            except Exception as e:
                logger.error("Unexpected error: %s", e, exc_info=True)
                await asyncio.sleep(self._current_delay)
                self._current_delay = min(
                    self._current_delay * self._backoff_factor, self._max_delay
                )

    async def stop(self):
        """Signal the connection loop to stop."""
        self._running = False

    def _subscription_message(self) -> dict:
        """Build aisstream.io subscription message.

        Bounding box format per AISstream docs: [[lat, lon], [lat, lon]].
        Overlapping boxes do NOT produce duplicate messages.
        """
        return {
            "APIKey": self.api_key,
            "BoundingBoxes": [
                [[53.85, -4.75], [72, 45.35]],       # Scandinavia, Baltic, Barents
                [[33.5, -13.01], [59.63, -0.88]],     # Atlantic coast: Portugal → UK
                [[30, -4.75], [42.75, 18.81]],         # West Mediterranean
                [[41.05, 27.51], [47, 42]],            # Black Sea
                [[19.56, 32.39], [30.6, 37.57]],       # Red Sea north
                [[49.38, -1.76], [55.93, 3.16]],       # English Channel / Southern North Sea
                [[22.42, 47.26], [30.92, 59.26]],      # Persian Gulf / Gulf of Oman
                [[41.31, 2.37], [46.4, 20.39]],        # Central Mediterranean / Adriatic
                [[10.3, 36.65], [24.69, 48.03]],       # Gulf of Aden / Arabian Sea
                [[10.83, 46.97], [27.27, 63.19]],      # Indian Ocean west
                [[52.32, 1.76], [56.59, 9.01]],        # Southern North Sea / German Bight
                [[28.62, 18.11], [41.51, 36.65]],      # East Mediterranean / Egypt
            ],
            "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
        }

    def _set_state(self, state: str):
        logger.info("WebSocket state: %s -> %s", self._state, state)
        self._state = state
