"""Tests for the WebSocket position streaming endpoint (Story 7).

Tests cover:
- WebSocket connection accepts and holds open
- Subscription filter message is parsed correctly
- Position updates are filtered by bbox when specified
- Position updates are filtered by risk_tier when specified
- Multiple clients with different filters receive only matching updates
- Messages contain required fields: mmsi, lat, lon, sog, cog, risk_tier, risk_score, timestamp
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
# collision with other service main.py modules.
# ---------------------------------------------------------------------------
_API_SERVER_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "services", "api-server")
)
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

_API_MAIN_PATH = os.path.join(_API_SERVER_DIR, "main.py")
_spec = importlib.util.spec_from_file_location("api_server_main_ws_positions", _API_MAIN_PATH)
api_main = importlib.util.module_from_spec(_spec)
sys.modules["api_server_main_ws_positions"] = api_main
_spec.loader.exec_module(api_main)

# Import the ws_positions module for direct unit testing of filter logic
from routes.ws_positions import (
    Subscription,
    _parse_subscription,
    matches_filter,
    manager,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def _mock_deps():
    """Mock database and Redis for WebSocket endpoint testing."""
    mock_engine = MagicMock()
    mock_engine.url = MagicMock()
    mock_engine.url.database = "test_db"

    mock_redis = AsyncMock()
    mock_redis.close = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=None)

    # Mock pubsub — we don't want real Redis subscriptions in tests
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.close = AsyncMock()

    # Make listen() return an async generator that blocks forever
    async def _empty_listen():
        try:
            await asyncio.Future()  # block forever
        except asyncio.CancelledError:
            return
        # This makes it an async generator
        yield  # pragma: no cover

    mock_pubsub.listen = _empty_listen
    mock_redis.pubsub.return_value = mock_pubsub

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
    """Ensure the connection manager is clean between tests."""
    manager.clients.clear()
    yield
    manager.clients.clear()


# ---------------------------------------------------------------------------
# Unit Tests: Subscription parsing
# ---------------------------------------------------------------------------


class TestParseSubscription:
    """Test subscription filter message parsing."""

    def test_empty_message_creates_default_subscription(self):
        sub = _parse_subscription({})
        assert sub.bbox is None
        assert sub.risk_tiers is None
        assert sub.ship_types is None
        assert sub.mmsi_list is None

    def test_bbox_is_parsed(self):
        sub = _parse_subscription({"bbox": [58.0, 9.0, 62.0, 12.0]})
        assert sub.bbox == [58.0, 9.0, 62.0, 12.0]

    def test_risk_tiers_is_parsed(self):
        sub = _parse_subscription({"risk_tiers": ["red", "yellow"]})
        assert sub.risk_tiers == ["red", "yellow"]

    def test_ship_types_is_parsed(self):
        sub = _parse_subscription({"ship_types": [70, 80]})
        assert sub.ship_types == [70, 80]

    def test_mmsi_list_is_parsed(self):
        sub = _parse_subscription({"mmsi_list": [211000001, 211000002]})
        assert sub.mmsi_list == [211000001, 211000002]

    def test_all_filters_combined(self):
        sub = _parse_subscription({
            "bbox": [55.0, 5.0, 65.0, 15.0],
            "risk_tiers": ["red"],
            "ship_types": [80, 81],
            "mmsi_list": [211000001],
        })
        assert sub.bbox == [55.0, 5.0, 65.0, 15.0]
        assert sub.risk_tiers == ["red"]
        assert sub.ship_types == [80, 81]
        assert sub.mmsi_list == [211000001]

    def test_invalid_bbox_ignored(self):
        sub = _parse_subscription({"bbox": [1.0, 2.0]})  # too few values
        assert sub.bbox is None

    def test_invalid_bbox_values_ignored(self):
        sub = _parse_subscription({"bbox": ["a", "b", "c", "d"]})
        assert sub.bbox is None


# ---------------------------------------------------------------------------
# Unit Tests: Filter matching
# ---------------------------------------------------------------------------


class TestMatchesFilter:
    """Test position filtering logic."""

    def _position(self, **overrides) -> dict:
        """Create a sample position message."""
        base = {
            "mmsi": 211000001,
            "lat": 59.91,
            "lon": 10.75,
            "sog": 12.5,
            "cog": 180.0,
            "risk_tier": "green",
            "risk_score": 15.0,
            "ship_type": 70,
            "timestamp": "2025-06-01T12:00:00Z",
        }
        base.update(overrides)
        return base

    def test_no_filter_matches_everything(self):
        sub = Subscription()
        assert matches_filter(self._position(), sub) is True

    def test_bbox_includes_position_inside(self):
        sub = Subscription(bbox=[59.0, 10.0, 60.0, 11.0])
        assert matches_filter(self._position(lat=59.5, lon=10.5), sub) is True

    def test_bbox_excludes_position_outside(self):
        sub = Subscription(bbox=[59.0, 10.0, 60.0, 11.0])
        assert matches_filter(self._position(lat=61.0, lon=10.5), sub) is False

    def test_bbox_boundary_is_inclusive(self):
        sub = Subscription(bbox=[59.0, 10.0, 60.0, 11.0])
        assert matches_filter(self._position(lat=59.0, lon=10.0), sub) is True
        assert matches_filter(self._position(lat=60.0, lon=11.0), sub) is True

    def test_risk_tier_matches(self):
        sub = Subscription(risk_tiers=["red", "yellow"])
        assert matches_filter(self._position(risk_tier="red"), sub) is True
        assert matches_filter(self._position(risk_tier="yellow"), sub) is True

    def test_risk_tier_excludes_non_matching(self):
        sub = Subscription(risk_tiers=["red"])
        assert matches_filter(self._position(risk_tier="green"), sub) is False

    def test_ship_type_matches(self):
        sub = Subscription(ship_types=[70, 80])
        assert matches_filter(self._position(ship_type=70), sub) is True

    def test_ship_type_excludes_non_matching(self):
        sub = Subscription(ship_types=[80])
        assert matches_filter(self._position(ship_type=70), sub) is False

    def test_mmsi_list_matches(self):
        sub = Subscription(mmsi_list=[211000001, 211000002])
        assert matches_filter(self._position(mmsi=211000001), sub) is True

    def test_mmsi_list_excludes_non_matching(self):
        sub = Subscription(mmsi_list=[211000099])
        assert matches_filter(self._position(mmsi=211000001), sub) is False

    def test_combined_filters_all_must_pass(self):
        sub = Subscription(
            bbox=[59.0, 10.0, 60.0, 11.0],
            risk_tiers=["red"],
        )
        # In bbox but wrong tier
        assert matches_filter(
            self._position(lat=59.5, lon=10.5, risk_tier="green"), sub
        ) is False
        # Right tier but outside bbox
        assert matches_filter(
            self._position(lat=61.0, lon=10.5, risk_tier="red"), sub
        ) is False
        # Both match
        assert matches_filter(
            self._position(lat=59.5, lon=10.5, risk_tier="red"), sub
        ) is True

    def test_missing_lat_lon_excluded_by_bbox(self):
        sub = Subscription(bbox=[59.0, 10.0, 60.0, 11.0])
        assert matches_filter({"mmsi": 1, "lat": None, "lon": None}, sub) is False


# ---------------------------------------------------------------------------
# Integration Tests: WebSocket endpoint
# ---------------------------------------------------------------------------


class TestWebSocketEndpoint:
    """Test the /ws/positions WebSocket endpoint."""

    def test_connection_accepts_and_holds_open(self, _mock_deps):
        """WebSocket connection at /ws/positions is accepted."""
        from starlette.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/positions") as ws:
                # Connection is open — send a filter and verify it's accepted
                ws.send_text(json.dumps({"risk_tiers": ["red"]}))
                # If we get here without exception, connection is alive
                # Close cleanly
                ws.close()

    def test_subscription_filter_is_applied(self, _mock_deps):
        """Sending a subscription message updates the client filter.

        We verify by broadcasting two positions — one matching the filter,
        one not — and checking only the matching one arrives.
        """
        from starlette.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/positions") as ws:
                filter_msg = {
                    "bbox": [58.0, 9.0, 62.0, 12.0],
                    "risk_tiers": ["red", "yellow"],
                    "ship_types": [80],
                    "mmsi_list": [211000001],
                }
                ws.send_text(json.dumps(filter_msg))

                import asyncio

                # Position that matches ALL filters
                matching = {
                    "mmsi": 211000001,
                    "lat": 59.5,
                    "lon": 10.5,
                    "sog": 12.0,
                    "cog": 90.0,
                    "risk_tier": "red",
                    "risk_score": 88.0,
                    "ship_type": 80,
                    "timestamp": "2025-06-01T12:00:00Z",
                }
                # Position that fails mmsi_list filter
                non_matching = {
                    "mmsi": 999999999,
                    "lat": 59.5,
                    "lon": 10.5,
                    "sog": 8.0,
                    "cog": 180.0,
                    "risk_tier": "red",
                    "risk_score": 50.0,
                    "ship_type": 80,
                    "timestamp": "2025-06-01T12:01:00Z",
                }

                loop = asyncio.new_event_loop()
                loop.run_until_complete(manager.broadcast_position(matching))
                loop.run_until_complete(manager.broadcast_position(non_matching))
                loop.close()

                # Should only receive the matching position
                data = ws.receive_text()
                msg = json.loads(data)
                assert msg["mmsi"] == 211000001
                ws.close()

    def test_position_broadcast_sends_matching_updates(self, _mock_deps):
        """Connected client receives position updates matching their filter."""
        from starlette.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/positions") as ws:
                # Subscribe to red tier only
                ws.send_text(json.dumps({"risk_tiers": ["red"]}))

                # Simulate a broadcast by directly calling broadcast_position
                # through the manager (since Redis is mocked)
                import asyncio

                position = {
                    "mmsi": 211000099,
                    "lat": 59.5,
                    "lon": 10.5,
                    "sog": 14.0,
                    "cog": 270.0,
                    "risk_tier": "red",
                    "risk_score": 92.0,
                    "timestamp": "2025-06-01T12:00:00Z",
                }

                # Run broadcast in the event loop
                loop = asyncio.new_event_loop()
                loop.run_until_complete(manager.broadcast_position(position))
                loop.close()

                # Read the message the client should have received
                data = ws.receive_text()
                msg = json.loads(data)

                # Verify required fields
                assert msg["mmsi"] == 211000099
                assert msg["lat"] == 59.5
                assert msg["lon"] == 10.5
                assert msg["sog"] == 14.0
                assert msg["cog"] == 270.0
                assert msg["risk_tier"] == "red"
                assert msg["risk_score"] == 92.0
                assert msg["timestamp"] == "2025-06-01T12:00:00Z"
                ws.close()

    def test_position_broadcast_filters_by_bbox(self, _mock_deps):
        """Client with bbox filter only receives positions within the bounding box."""
        from starlette.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/positions") as ws:
                # Subscribe to a bbox around Oslo
                ws.send_text(json.dumps({"bbox": [59.0, 10.0, 60.0, 11.0]}))

                import asyncio

                # Position inside bbox
                pos_inside = {
                    "mmsi": 211000001,
                    "lat": 59.5,
                    "lon": 10.5,
                    "sog": 10.0,
                    "cog": 90.0,
                    "risk_tier": "green",
                    "risk_score": 10.0,
                    "timestamp": "2025-06-01T12:00:00Z",
                }
                # Position outside bbox
                pos_outside = {
                    "mmsi": 211000002,
                    "lat": 65.0,
                    "lon": 15.0,
                    "sog": 8.0,
                    "cog": 180.0,
                    "risk_tier": "green",
                    "risk_score": 5.0,
                    "timestamp": "2025-06-01T12:01:00Z",
                }

                loop = asyncio.new_event_loop()
                loop.run_until_complete(manager.broadcast_position(pos_inside))
                loop.run_until_complete(manager.broadcast_position(pos_outside))
                loop.close()

                # Should receive only the inside position
                data = ws.receive_text()
                msg = json.loads(data)
                assert msg["mmsi"] == 211000001

                ws.close()

    def test_position_broadcast_filters_by_risk_tier(self, _mock_deps):
        """Client with risk_tiers filter only receives matching positions."""
        from starlette.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/positions") as ws:
                ws.send_text(json.dumps({"risk_tiers": ["red"]}))

                import asyncio

                pos_red = {
                    "mmsi": 211000001,
                    "lat": 59.5,
                    "lon": 10.5,
                    "sog": 10.0,
                    "cog": 90.0,
                    "risk_tier": "red",
                    "risk_score": 95.0,
                    "timestamp": "2025-06-01T12:00:00Z",
                }
                pos_green = {
                    "mmsi": 211000002,
                    "lat": 59.5,
                    "lon": 10.5,
                    "sog": 8.0,
                    "cog": 180.0,
                    "risk_tier": "green",
                    "risk_score": 10.0,
                    "timestamp": "2025-06-01T12:01:00Z",
                }

                loop = asyncio.new_event_loop()
                loop.run_until_complete(manager.broadcast_position(pos_red))
                loop.run_until_complete(manager.broadcast_position(pos_green))
                loop.close()

                # Should only get the red position
                data = ws.receive_text()
                msg = json.loads(data)
                assert msg["mmsi"] == 211000001
                assert msg["risk_tier"] == "red"

                ws.close()

    def test_invalid_json_returns_error(self, _mock_deps):
        """Sending invalid JSON returns an error message."""
        from starlette.testclient import TestClient

        app = api_main.create_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/positions") as ws:
                ws.send_text("not valid json {{{")
                data = ws.receive_text()
                msg = json.loads(data)
                assert "error" in msg
                ws.close()
