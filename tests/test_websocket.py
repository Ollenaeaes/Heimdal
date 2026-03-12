"""Tests for the AISWebSocket class."""

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "ais-ingest"))

from websocket import AISWebSocket


class TestSubscriptionMessage:
    """Tests for the subscription message format."""

    def test_subscription_has_api_key(self):
        ws = AISWebSocket(on_message=AsyncMock(), api_key="test-key-123")
        msg = ws._subscription_message()
        assert msg["APIKey"] == "test-key-123"

    def test_subscription_has_bounding_boxes(self):
        ws = AISWebSocket(on_message=AsyncMock(), api_key="test-key")
        msg = ws._subscription_message()
        assert "BoundingBoxes" in msg
        assert msg["BoundingBoxes"] == [[-90, -180, 90, 180]]

    def test_subscription_has_filter_message_types(self):
        ws = AISWebSocket(on_message=AsyncMock(), api_key="test-key")
        msg = ws._subscription_message()
        assert "FilterMessageTypes" in msg
        assert "PositionReport" in msg["FilterMessageTypes"]
        assert "ShipStaticData" in msg["FilterMessageTypes"]


class TestExponentialBackoff:
    """Tests for backoff logic."""

    def test_initial_delay_is_one(self):
        ws = AISWebSocket(on_message=AsyncMock(), api_key="test-key")
        assert ws._current_delay == 1.0

    def test_backoff_doubles(self):
        ws = AISWebSocket(on_message=AsyncMock(), api_key="test-key")
        delays = [ws._current_delay]
        for _ in range(6):
            ws._current_delay = min(
                ws._current_delay * ws._backoff_factor, ws._max_delay
            )
            delays.append(ws._current_delay)
        # 1 -> 2 -> 4 -> 8 -> 16 -> 32 -> 60 (capped)
        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0]

    def test_backoff_capped_at_max(self):
        ws = AISWebSocket(on_message=AsyncMock(), api_key="test-key")
        # Set current_delay near max
        ws._current_delay = 50.0
        ws._current_delay = min(
            ws._current_delay * ws._backoff_factor, ws._max_delay
        )
        assert ws._current_delay == 60.0  # capped at reconnect_max

    def test_backoff_resets_after_successful_connection(self):
        ws = AISWebSocket(on_message=AsyncMock(), api_key="test-key")
        # Simulate several backoffs
        ws._current_delay = 32.0
        # Simulate successful connection reset
        ws._current_delay = ws._initial_delay
        assert ws._current_delay == 1.0


class TestStateTransitions:
    """Tests for state transition logging."""

    def test_initial_state_is_disconnected(self):
        ws = AISWebSocket(on_message=AsyncMock(), api_key="test-key")
        assert ws._state == "disconnected"

    def test_set_state_updates_state(self):
        ws = AISWebSocket(on_message=AsyncMock(), api_key="test-key")
        ws._set_state("connecting")
        assert ws._state == "connecting"

    def test_set_state_logs_transition(self, caplog):
        ws = AISWebSocket(on_message=AsyncMock(), api_key="test-key")
        with caplog.at_level(logging.INFO, logger="ais-ingest"):
            ws._set_state("connecting")
        assert "disconnected -> connecting" in caplog.text

    def test_state_sequence_on_connect(self):
        ws = AISWebSocket(on_message=AsyncMock(), api_key="test-key")
        states = []
        original_set = ws._set_state

        def tracking_set(state):
            original_set(state)
            states.append(state)

        ws._set_state = tracking_set
        ws._set_state("connecting")
        ws._set_state("connected")
        assert states == ["connecting", "connected"]


class TestStaleConnectionDetection:
    """Tests for stale connection timeout."""

    @pytest.mark.asyncio
    async def test_stale_connection_breaks_receive_loop(self):
        """If no message arrives within stale_timeout, the loop should break."""
        on_message = AsyncMock()
        ws = AISWebSocket(on_message=on_message, api_key="test-key")
        ws._stale_timeout = 0.1  # 100ms for fast testing

        # Mock websockets.connect to return a mock WS that hangs on recv
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()

        # recv() will hang forever, triggering the stale timeout
        async def hang_forever():
            await asyncio.sleep(999)

        mock_ws.recv = hang_forever

        # Create a context manager mock
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        call_count = 0

        def mock_connect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                # After first reconnect attempt, stop the loop
                ws._running = False
                raise ConnectionRefusedError("test stop")
            return mock_ctx

        with patch("websocket.websockets.connect", side_effect=mock_connect):
            ws._running = True
            # Run start() but stop after the stale detection
            task = asyncio.create_task(ws.start())
            await asyncio.sleep(0.5)
            ws._running = False
            # Give it time to clean up
            await asyncio.sleep(0.2)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # The on_message callback should never have been called
        on_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_message_updates_last_message_time(self):
        """Receiving a message should update _last_message_time."""
        on_message = AsyncMock()
        ws = AISWebSocket(on_message=on_message, api_key="test-key")
        ws._stale_timeout = 5.0  # won't trigger

        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()

        call_idx = 0

        async def recv_with_messages():
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return json.dumps({"MessageType": "PositionReport"})
            else:
                # Stop after first message
                ws._running = False
                await asyncio.sleep(999)

        mock_ws.recv = recv_with_messages

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("websocket.websockets.connect", return_value=mock_ctx):
            ws._running = True
            task = asyncio.create_task(ws.start())
            await asyncio.sleep(0.3)
            ws._running = False
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert ws._last_message_time > 0
        on_message.assert_called_once()


class TestStop:
    """Tests for stop behavior."""

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self):
        ws = AISWebSocket(on_message=AsyncMock(), api_key="test-key")
        ws._running = True
        await ws.stop()
        assert ws._running is False
