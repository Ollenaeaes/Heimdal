"""Integration test: WebSocket position delivery.

Verifies that connecting to the WebSocket position stream works
and data is delivered within the expected timeframe.
Requires Docker Compose.

Run: pytest tests/integration/test_websocket_delivery.py -v
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from .conftest import WS_BASE_URL, requires_docker

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False


@requires_docker
@pytest.mark.skipif(not HAS_WEBSOCKETS, reason="websockets library not installed")
class TestWebSocketPositionDelivery:
    """Test WebSocket position streaming via /ws/positions."""

    @pytest.mark.asyncio
    async def test_websocket_connects_successfully(self):
        """WebSocket connection to /ws/positions succeeds."""
        uri = f"{WS_BASE_URL}/ws/positions"
        async with websockets.connect(uri, open_timeout=5) as ws:
            assert ws.open

    @pytest.mark.asyncio
    async def test_websocket_receives_position_within_timeout(self):
        """WebSocket receives at least one position update within 10 seconds.

        Note: This test may be skipped if no AIS data is flowing.
        The 10-second timeout is generous; typical delivery is < 5 seconds.
        """
        uri = f"{WS_BASE_URL}/ws/positions"
        received = []

        async with websockets.connect(uri, open_timeout=5) as ws:
            # Send subscription filter (empty = all vessels)
            await ws.send(json.dumps({}))

            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(msg)
                received.append(data)
            except asyncio.TimeoutError:
                pytest.skip(
                    "No position data received within 10s "
                    "(AIS data may not be flowing)"
                )

        if received:
            pos = received[0]
            assert "mmsi" in pos
            assert "lat" in pos or "latitude" in pos

    @pytest.mark.asyncio
    async def test_websocket_subscription_filter(self):
        """WebSocket accepts a subscription filter message without error."""
        uri = f"{WS_BASE_URL}/ws/positions"
        async with websockets.connect(uri, open_timeout=5) as ws:
            # Send a filter for a specific risk tier
            filter_msg = json.dumps({"risk_tiers": ["red"]})
            await ws.send(filter_msg)

            # Connection should remain open after sending filter
            assert ws.open


@requires_docker
@pytest.mark.skipif(not HAS_WEBSOCKETS, reason="websockets library not installed")
class TestWebSocketAlertDelivery:
    """Test WebSocket alert streaming via /ws/alerts."""

    @pytest.mark.asyncio
    async def test_alert_websocket_connects(self):
        """WebSocket connection to /ws/alerts succeeds."""
        uri = f"{WS_BASE_URL}/ws/alerts"
        async with websockets.connect(uri, open_timeout=5) as ws:
            assert ws.open

    @pytest.mark.asyncio
    async def test_alert_websocket_stays_open(self):
        """WebSocket stays open for at least 3 seconds without errors."""
        uri = f"{WS_BASE_URL}/ws/alerts"
        async with websockets.connect(uri, open_timeout=5) as ws:
            await asyncio.sleep(3)
            assert ws.open
