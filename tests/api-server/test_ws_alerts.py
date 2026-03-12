"""Tests for WebSocket alert streaming (Story 8).

Tests cover:
- WebSocket connection stays open
- Risk change events are forwarded to all clients
- Anomaly events are forwarded to all clients
- Alert payload includes type, mmsi, vessel_name, and event-specific fields
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import the api-server main module explicitly by file path to avoid
# collision with other service main.py files.
# ---------------------------------------------------------------------------
_API_SERVER_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "services", "api-server")
)
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

_API_MAIN_PATH = os.path.join(_API_SERVER_DIR, "main.py")
_spec = importlib.util.spec_from_file_location("api_server_main_ws_alerts", _API_MAIN_PATH)
api_main = importlib.util.module_from_spec(_spec)
sys.modules["api_server_main_ws_alerts"] = api_main
_spec.loader.exec_module(api_main)

from routes.ws_alerts import manager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def _mock_deps():
    """Mock database and Redis for WebSocket testing."""
    mock_engine = MagicMock()
    mock_engine.url = MagicMock()
    mock_engine.url.database = "test_db"

    mock_redis = AsyncMock()
    mock_redis.close = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=None)

    # Mock pubsub — block forever so the listener doesn't interfere
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.close = AsyncMock()

    async def _empty_listen():
        try:
            await asyncio.Future()  # block forever
        except asyncio.CancelledError:
            return
        yield  # pragma: no cover

    mock_pubsub.listen = _empty_listen
    # pubsub() is synchronous in redis-py, so use MagicMock (not AsyncMock)
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

    with (
        patch.object(api_main, "get_engine", return_value=mock_engine),
        patch.object(api_main, "dispose_engine", new_callable=AsyncMock),
        patch.object(api_main, "aioredis") as mock_aioredis,
    ):
        mock_aioredis.from_url.return_value = mock_redis
        yield {
            "engine": mock_engine,
            "redis": mock_redis,
            "aioredis": mock_aioredis,
            "pubsub": mock_pubsub,
        }


@pytest.fixture(autouse=True)
def _clean_manager():
    """Ensure the connection manager and listener task are clean between tests."""
    import routes.ws_alerts as ws_alerts_mod

    manager._connections.clear()
    ws_alerts_mod._redis_listener_task = None
    yield
    manager._connections.clear()
    ws_alerts_mod._redis_listener_task = None


# ---------------------------------------------------------------------------
# Sample events
# ---------------------------------------------------------------------------

_RISK_CHANGE_EVENT = {
    "type": "risk_change",
    "mmsi": 211234567,
    "vessel_name": "NORDIC EXPLORER",
    "old_tier": "green",
    "new_tier": "yellow",
    "risk_score": 42,
}

_ANOMALY_EVENT = {
    "type": "anomaly",
    "mmsi": 259876543,
    "vessel_name": "AEGEAN SPIRIT",
    "rule_id": "ais_gap",
    "severity": "high",
    "details": {"gap_hours": 12},
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWebSocketConnection:
    """Test WebSocket connection stays open."""

    def test_websocket_connects_successfully(self, _mock_deps):
        """GIVEN ws://localhost:8000/ws/alerts WHEN connected THEN connection is accepted and stays open."""
        from starlette.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/alerts") as ws:
                # Connection is open — verify we can interact
                assert ws is not None
                ws.close()


class TestRiskChangeForwarding:
    """Test risk change events are forwarded to all clients."""

    def test_risk_change_event_forwarded(self, _mock_deps):
        """GIVEN a risk_change event WHEN broadcast THEN connected client receives it."""
        from starlette.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/alerts") as ws:
                # Broadcast a risk_change event through the manager
                loop = asyncio.new_event_loop()
                loop.run_until_complete(manager.broadcast(_RISK_CHANGE_EVENT))
                loop.close()

                data = json.loads(ws.receive_text())

                assert data["type"] == "risk_change"
                assert data["mmsi"] == 211234567
                assert data["vessel_name"] == "NORDIC EXPLORER"
                assert data["old_tier"] == "green"
                assert data["new_tier"] == "yellow"
                assert data["risk_score"] == 42
                ws.close()

    def test_risk_change_broadcast_to_multiple_clients(self, _mock_deps):
        """GIVEN multiple connected clients WHEN risk_change event THEN all receive it."""
        from starlette.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/alerts") as ws1:
                with client.websocket_connect("/ws/alerts") as ws2:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(manager.broadcast(_RISK_CHANGE_EVENT))
                    loop.close()

                    data1 = json.loads(ws1.receive_text())
                    data2 = json.loads(ws2.receive_text())

                    assert data1["type"] == "risk_change"
                    assert data2["type"] == "risk_change"
                    assert data1["mmsi"] == _RISK_CHANGE_EVENT["mmsi"]
                    assert data2["mmsi"] == _RISK_CHANGE_EVENT["mmsi"]
                    ws2.close()
                ws1.close()


class TestAnomalyForwarding:
    """Test anomaly events are forwarded to all clients."""

    def test_anomaly_event_forwarded(self, _mock_deps):
        """GIVEN an anomaly event WHEN broadcast THEN connected client receives it."""
        from starlette.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/alerts") as ws:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(manager.broadcast(_ANOMALY_EVENT))
                loop.close()

                data = json.loads(ws.receive_text())

                assert data["type"] == "anomaly"
                assert data["mmsi"] == 259876543
                assert data["vessel_name"] == "AEGEAN SPIRIT"
                assert data["rule_id"] == "ais_gap"
                assert data["severity"] == "high"
                assert data["details"] == {"gap_hours": 12}
                ws.close()

    def test_anomaly_broadcast_to_multiple_clients(self, _mock_deps):
        """GIVEN multiple connected clients WHEN anomaly event THEN all receive it."""
        from starlette.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/alerts") as ws1:
                with client.websocket_connect("/ws/alerts") as ws2:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(manager.broadcast(_ANOMALY_EVENT))
                    loop.close()

                    data1 = json.loads(ws1.receive_text())
                    data2 = json.loads(ws2.receive_text())

                    assert data1["type"] == "anomaly"
                    assert data2["type"] == "anomaly"
                    assert data1["mmsi"] == _ANOMALY_EVENT["mmsi"]
                    assert data2["mmsi"] == _ANOMALY_EVENT["mmsi"]
                    ws2.close()
                ws1.close()


class TestAlertPayload:
    """Test alert payload includes required fields."""

    def test_risk_change_payload_includes_required_fields(self, _mock_deps):
        """GIVEN risk_change alert WHEN sent THEN payload includes type, mmsi, vessel_name, and event fields."""
        from starlette.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/alerts") as ws:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(manager.broadcast(_RISK_CHANGE_EVENT))
                loop.close()

                data = json.loads(ws.receive_text())

                # Required fields for risk_change
                assert data["type"] == "risk_change"
                assert data["mmsi"] == 211234567
                assert data["vessel_name"] == "NORDIC EXPLORER"
                # Event-specific fields
                assert "old_tier" in data
                assert "new_tier" in data
                assert "risk_score" in data
                ws.close()

    def test_anomaly_payload_includes_required_fields(self, _mock_deps):
        """GIVEN anomaly alert WHEN sent THEN payload includes type, mmsi, vessel_name, and event fields."""
        from starlette.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/alerts") as ws:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(manager.broadcast(_ANOMALY_EVENT))
                loop.close()

                data = json.loads(ws.receive_text())

                # Required fields for anomaly
                assert data["type"] == "anomaly"
                assert data["mmsi"] == 259876543
                assert data["vessel_name"] == "AEGEAN SPIRIT"
                # Event-specific fields
                assert "rule_id" in data
                assert "severity" in data
                assert "details" in data
                ws.close()

    def test_both_event_types_on_same_connection(self, _mock_deps):
        """GIVEN both risk_change and anomaly events WHEN broadcast THEN both forwarded to same client."""
        from starlette.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/alerts") as ws:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(manager.broadcast(_RISK_CHANGE_EVENT))
                loop.run_until_complete(manager.broadcast(_ANOMALY_EVENT))
                loop.close()

                data1 = json.loads(ws.receive_text())
                data2 = json.loads(ws.receive_text())

                types = {data1["type"], data2["type"]}
                assert types == {"risk_change", "anomaly"}
                ws.close()


class TestRedisChannelMapping:
    """Test that Redis channel names map to correct alert types."""

    def test_risk_changes_channel_maps_to_risk_change_type(self):
        """heimdal:risk_changes channel maps to type 'risk_change'."""
        from routes.ws_alerts import _CHANNEL_TO_TYPE, RISK_CHANGES_CHANNEL

        assert _CHANNEL_TO_TYPE[RISK_CHANGES_CHANNEL] == "risk_change"

    def test_anomalies_channel_maps_to_anomaly_type(self):
        """heimdal:anomalies channel maps to type 'anomaly'."""
        from routes.ws_alerts import _CHANNEL_TO_TYPE, ANOMALIES_CHANNEL

        assert _CHANNEL_TO_TYPE[ANOMALIES_CHANNEL] == "anomaly"

    def test_redis_listener_subscribes_to_both_channels(self, _mock_deps):
        """The Redis listener subscribes to both heimdal:risk_changes and heimdal:anomalies."""
        from starlette.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/alerts") as ws:
                import time
                time.sleep(0.1)

                # Verify pubsub.subscribe was called with both channels
                _mock_deps["pubsub"].subscribe.assert_called_once_with(
                    "heimdal:risk_changes", "heimdal:anomalies"
                )
                ws.close()
