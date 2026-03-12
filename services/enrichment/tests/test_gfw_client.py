"""Tests for the GFW API client.

Uses httpx MockTransport to simulate GFW API responses without
requiring real API access.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

# Add paths for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from gfw_client import (
    GFWAPIError,
    GFWAuthError,
    GFWClient,
    INITIAL_BACKOFF,
    MAX_RETRIES,
    RETRYABLE_STATUS_CODES,
)
from shared.config import settings


# ===================================================================
# Helpers
# ===================================================================


def make_token_response(expires_in: int = 3600) -> dict:
    """Create a mock GFW token response."""
    return {
        "token": "mock-jwt-access-token",
        "expiresAt": time.time() + expires_in,
    }


def make_events_page(entries: list[dict], total: int, offset: int = 0) -> dict:
    """Create a mock paginated events response."""
    return {
        "entries": entries,
        "total": total,
        "offset": offset,
    }


def make_next_offset_page(
    entries: list[dict], next_offset: int | None = None
) -> dict:
    """Create a mock response with nextOffset pagination."""
    result: dict[str, Any] = {"entries": entries}
    if next_offset is not None:
        result["nextOffset"] = next_offset
    return result


# ===================================================================
# JWT Authentication Tests
# ===================================================================


class TestAuthentication:
    """Test JWT token acquisition from GFW API token."""

    @pytest.mark.asyncio
    async def test_jwt_token_acquisition(self):
        """Token is acquired by POSTing API token to /auth/token."""
        auth_called = False

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal auth_called
            if request.url.path == "/auth/token" and request.method == "POST":
                # Verify the API token is sent as Bearer token
                assert request.headers["Authorization"] == "Bearer test-api-token"
                auth_called = True
                return httpx.Response(
                    200,
                    json=make_token_response(),
                )
            if request.url.path == "/v3/test":
                # Verify JWT is used for subsequent requests
                assert request.headers["Authorization"] == "Bearer mock-jwt-access-token"
                return httpx.Response(200, json={"ok": True})
            return httpx.Response(404)

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            result = await client.get("/v3/test")
            assert auth_called
            assert result == {"ok": True}
            assert client._access_token == "mock-jwt-access-token"
        finally:
            await client._http.aclose()

    @pytest.mark.asyncio
    async def test_auth_failure_raises_error(self):
        """GFWAuthError is raised when token endpoint returns an error."""

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/auth/token":
                return httpx.Response(401, json={"error": "Invalid API token"})
            return httpx.Response(404)

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="bad-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            with pytest.raises(GFWAuthError, match="authentication failed"):
                await client.get("/v3/test")
        finally:
            await client._http.aclose()

    @pytest.mark.asyncio
    async def test_jwt_used_in_subsequent_requests(self):
        """After authentication, the JWT is sent as Bearer token on requests."""
        request_tokens = []

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/auth/token":
                return httpx.Response(200, json=make_token_response())
            # Record the auth header for non-auth requests
            request_tokens.append(request.headers.get("Authorization"))
            return httpx.Response(200, json={"data": "ok"})

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            await client.get("/v3/endpoint1")
            await client.get("/v3/endpoint2")
            assert all(t == "Bearer mock-jwt-access-token" for t in request_tokens)
            assert len(request_tokens) == 2
        finally:
            await client._http.aclose()


# ===================================================================
# Token Refresh Tests
# ===================================================================


class TestTokenRefresh:
    """Test automatic token refresh on expiry."""

    @pytest.mark.asyncio
    async def test_auto_refresh_on_expiry(self):
        """A new JWT is fetched when the current one is expired."""
        auth_count = 0

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal auth_count
            if request.url.path == "/auth/token":
                auth_count += 1
                return httpx.Response(
                    200,
                    json={
                        "token": f"jwt-token-{auth_count}",
                        "expiresAt": time.time() + 3600,
                    },
                )
            return httpx.Response(200, json={"data": "ok"})

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            # First request — triggers auth
            await client.get("/v3/test")
            assert auth_count == 1
            assert client._access_token == "jwt-token-1"

            # Simulate token expiry by setting expires_at to the past
            client._token_expires_at = time.time() - 10

            # Second request — triggers re-auth
            await client.get("/v3/test")
            assert auth_count == 2
            assert client._access_token == "jwt-token-2"
        finally:
            await client._http.aclose()

    @pytest.mark.asyncio
    async def test_no_refresh_when_token_valid(self):
        """No re-auth when the JWT is still valid."""
        auth_count = 0

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal auth_count
            if request.url.path == "/auth/token":
                auth_count += 1
                return httpx.Response(200, json=make_token_response(expires_in=7200))
            return httpx.Response(200, json={"data": "ok"})

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            await client.get("/v3/test")
            await client.get("/v3/test")
            await client.get("/v3/test")
            # Only one auth call despite three requests
            assert auth_count == 1
        finally:
            await client._http.aclose()

    @pytest.mark.asyncio
    async def test_refresh_buffer_period(self):
        """Token is refreshed 60 seconds before actual expiry."""
        auth_count = 0

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal auth_count
            if request.url.path == "/auth/token":
                auth_count += 1
                return httpx.Response(
                    200,
                    json={
                        "token": f"jwt-{auth_count}",
                        # Expire in 30 seconds — within the 60s buffer
                        "expiresAt": time.time() + 30,
                    },
                )
            return httpx.Response(200, json={"data": "ok"})

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            # First request — auth, token expires_at = now + 30 - 60 = now - 30 (already "expired")
            await client.get("/v3/test")
            assert auth_count == 1

            # Second request — should re-auth since buffer makes it expired
            await client.get("/v3/test")
            assert auth_count == 2
        finally:
            await client._http.aclose()


# ===================================================================
# Rate Limiting Tests
# ===================================================================


class TestRateLimiting:
    """Test rate limiting enforces configured limit."""

    @pytest.mark.asyncio
    async def test_rate_limiting_enforces_interval(self):
        """Requests are spaced at least 1/rate_limit seconds apart."""
        request_times: list[float] = []

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/auth/token":
                return httpx.Response(200, json=make_token_response())
            request_times.append(time.monotonic())
            return httpx.Response(200, json={"data": "ok"})

        transport = httpx.MockTransport(mock_handler)

        rate_limit = 10  # 10 req/s → 0.1s interval
        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=rate_limit,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            # Make 5 sequential requests
            for _ in range(5):
                await client.get("/v3/test")

            # Verify minimum spacing between consecutive requests
            expected_interval = 1.0 / rate_limit
            for i in range(1, len(request_times)):
                actual_interval = request_times[i] - request_times[i - 1]
                # Allow 10ms tolerance for timing imprecision
                assert actual_interval >= expected_interval - 0.01, (
                    f"Request {i} came {actual_interval:.4f}s after previous, "
                    f"expected >= {expected_interval:.4f}s"
                )
        finally:
            await client._http.aclose()

    @pytest.mark.asyncio
    async def test_rate_limit_uses_config_value(self):
        """Rate limit is taken from the constructor parameter."""
        client = GFWClient(
            api_token="test",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=42,
        )
        assert client._rate_limit == 42
        assert client._request_interval == pytest.approx(1.0 / 42)


# ===================================================================
# Retry Logic Tests
# ===================================================================


class TestRetryLogic:
    """Test retry with exponential backoff on transient errors."""

    @pytest.mark.asyncio
    async def test_retry_on_429(self):
        """Retries on 429 (Too Many Requests) with exponential backoff."""
        attempt_count = 0

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempt_count
            if request.url.path == "/auth/token":
                return httpx.Response(200, json=make_token_response())
            attempt_count += 1
            if attempt_count <= 2:
                return httpx.Response(429, text="Too Many Requests")
            return httpx.Response(200, json={"data": "success"})

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await client.get("/v3/test")

            assert result == {"data": "success"}
            assert attempt_count == 3
            # Verify exponential backoff: 1s, 2s
            assert mock_sleep.await_count >= 2
        finally:
            await client._http.aclose()

    @pytest.mark.asyncio
    async def test_retry_on_500(self):
        """Retries on 500 (Internal Server Error)."""
        attempt_count = 0

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempt_count
            if request.url.path == "/auth/token":
                return httpx.Response(200, json=make_token_response())
            attempt_count += 1
            if attempt_count == 1:
                return httpx.Response(500, text="Internal Server Error")
            return httpx.Response(200, json={"data": "recovered"})

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await client.get("/v3/test")

            assert result == {"data": "recovered"}
            assert attempt_count == 2
        finally:
            await client._http.aclose()

    @pytest.mark.asyncio
    async def test_retry_on_502(self):
        """Retries on 502 (Bad Gateway)."""
        attempt_count = 0

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempt_count
            if request.url.path == "/auth/token":
                return httpx.Response(200, json=make_token_response())
            attempt_count += 1
            if attempt_count == 1:
                return httpx.Response(502, text="Bad Gateway")
            return httpx.Response(200, json={"data": "ok"})

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await client.get("/v3/test")
            assert result == {"data": "ok"}
            assert attempt_count == 2
        finally:
            await client._http.aclose()

    @pytest.mark.asyncio
    async def test_retry_on_503(self):
        """Retries on 503 (Service Unavailable)."""
        attempt_count = 0

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempt_count
            if request.url.path == "/auth/token":
                return httpx.Response(200, json=make_token_response())
            attempt_count += 1
            if attempt_count == 1:
                return httpx.Response(503, text="Service Unavailable")
            return httpx.Response(200, json={"data": "ok"})

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await client.get("/v3/test")
            assert result == {"data": "ok"}
            assert attempt_count == 2
        finally:
            await client._http.aclose()

    @pytest.mark.asyncio
    async def test_max_retries_exceeded_raises_error(self):
        """GFWAPIError is raised after MAX_RETRIES+1 failed attempts."""
        attempt_count = 0

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempt_count
            if request.url.path == "/auth/token":
                return httpx.Response(200, json=make_token_response())
            attempt_count += 1
            return httpx.Response(503, text="Service Unavailable")

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(GFWAPIError, match="failed after"):
                    await client.get("/v3/test")

            assert attempt_count == MAX_RETRIES + 1
        finally:
            await client._http.aclose()

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self):
        """Backoff doubles on each retry: 1s, 2s, 4s."""
        sleep_durations: list[float] = []

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/auth/token":
                return httpx.Response(200, json=make_token_response())
            return httpx.Response(500, text="Server Error")

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        async def capture_sleep(duration):
            sleep_durations.append(duration)

        try:
            with patch("asyncio.sleep", side_effect=capture_sleep):
                with pytest.raises(GFWAPIError):
                    await client.get("/v3/test")

            # Filter out rate-limiting sleeps (very small) vs retry sleeps
            retry_sleeps = [d for d in sleep_durations if d >= INITIAL_BACKOFF * 0.5]
            assert len(retry_sleeps) == MAX_RETRIES
            # Verify exponential backoff: 1, 2, 4
            for i, expected in enumerate([1.0, 2.0, 4.0]):
                assert retry_sleeps[i] == pytest.approx(expected, rel=0.1), (
                    f"Retry {i+1} backoff was {retry_sleeps[i]}, expected {expected}"
                )
        finally:
            await client._http.aclose()

    @pytest.mark.asyncio
    async def test_no_retry_on_4xx_non_429(self):
        """Non-retryable 4xx errors (e.g. 400, 404) fail immediately."""

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/auth/token":
                return httpx.Response(200, json=make_token_response())
            return httpx.Response(400, text="Bad Request")

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            with pytest.raises(GFWAPIError) as exc_info:
                await client.get("/v3/test")
            assert exc_info.value.status_code == 400
        finally:
            await client._http.aclose()

    @pytest.mark.asyncio
    async def test_retry_after_header_respected(self):
        """Retry-After header value is used as sleep duration when present."""
        sleep_durations: list[float] = []
        attempt_count = 0

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempt_count
            if request.url.path == "/auth/token":
                return httpx.Response(200, json=make_token_response())
            attempt_count += 1
            if attempt_count == 1:
                return httpx.Response(
                    429,
                    text="Rate Limited",
                    headers={"Retry-After": "5"},
                )
            return httpx.Response(200, json={"data": "ok"})

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        async def capture_sleep(duration):
            sleep_durations.append(duration)

        try:
            with patch("asyncio.sleep", side_effect=capture_sleep):
                result = await client.get("/v3/test")

            assert result == {"data": "ok"}
            # The retry sleep should be 5.0 (from Retry-After header)
            retry_sleeps = [d for d in sleep_durations if d >= 1.0]
            assert 5.0 in retry_sleeps
        finally:
            await client._http.aclose()


# ===================================================================
# Pagination Tests
# ===================================================================


class TestPagination:
    """Test automatic pagination to retrieve all results."""

    @pytest.mark.asyncio
    async def test_single_page_response(self):
        """A response with all results in one page returns them directly."""

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/auth/token":
                return httpx.Response(200, json=make_token_response())
            return httpx.Response(
                200,
                json=make_events_page(
                    entries=[{"id": "e1"}, {"id": "e2"}],
                    total=2,
                ),
            )

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            results = await client.get_all_pages("/v3/events", page_size=10)
            assert len(results) == 2
            assert results[0]["id"] == "e1"
            assert results[1]["id"] == "e2"
        finally:
            await client._http.aclose()

    @pytest.mark.asyncio
    async def test_multi_page_response(self):
        """Multiple pages are fetched until all results are collected."""
        call_count = 0

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            if request.url.path == "/auth/token":
                return httpx.Response(200, json=make_token_response())

            call_count += 1
            offset = int(request.url.params.get("offset", "0"))

            if offset == 0:
                return httpx.Response(
                    200,
                    json=make_events_page(
                        entries=[{"id": f"e{i}"} for i in range(1, 4)],
                        total=7,
                        offset=0,
                    ),
                )
            elif offset == 3:
                return httpx.Response(
                    200,
                    json=make_events_page(
                        entries=[{"id": f"e{i}"} for i in range(4, 7)],
                        total=7,
                        offset=3,
                    ),
                )
            else:
                return httpx.Response(
                    200,
                    json=make_events_page(
                        entries=[{"id": "e7"}],
                        total=7,
                        offset=6,
                    ),
                )

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            results = await client.get_all_pages("/v3/events", page_size=3)
            assert len(results) == 7
            assert [r["id"] for r in results] == [f"e{i}" for i in range(1, 8)]
            assert call_count == 3  # 3 pages fetched
        finally:
            await client._http.aclose()

    @pytest.mark.asyncio
    async def test_empty_response(self):
        """An endpoint returning no results returns an empty list."""

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/auth/token":
                return httpx.Response(200, json=make_token_response())
            return httpx.Response(
                200,
                json=make_events_page(entries=[], total=0),
            )

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            results = await client.get_all_pages("/v3/events", page_size=10)
            assert results == []
        finally:
            await client._http.aclose()

    @pytest.mark.asyncio
    async def test_pagination_passes_params(self):
        """Custom params are forwarded alongside pagination params."""
        received_params: list[dict] = []

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/auth/token":
                return httpx.Response(200, json=make_token_response())
            received_params.append(dict(request.url.params))
            return httpx.Response(
                200,
                json=make_events_page(entries=[{"id": "e1"}], total=1),
            )

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            await client.get_all_pages(
                "/v3/events",
                params={"vessel-id": "abc123", "datasets[0]": "fishing"},
                page_size=50,
            )
            assert len(received_params) == 1
            assert received_params[0]["vessel-id"] == "abc123"
            assert received_params[0]["datasets[0]"] == "fishing"
            assert received_params[0]["limit"] == "50"
            assert received_params[0]["offset"] == "0"
        finally:
            await client._http.aclose()

    @pytest.mark.asyncio
    async def test_next_offset_pagination(self):
        """Pagination via nextOffset cursor follows the chain."""
        call_count = 0

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            if request.url.path == "/auth/token":
                return httpx.Response(200, json=make_token_response())

            call_count += 1
            offset = request.url.params.get("offset")

            if offset is None:
                return httpx.Response(
                    200,
                    json=make_next_offset_page(
                        entries=[{"id": "e1"}, {"id": "e2"}],
                        next_offset=2,
                    ),
                )
            elif offset == "2":
                return httpx.Response(
                    200,
                    json=make_next_offset_page(
                        entries=[{"id": "e3"}],
                        next_offset=None,
                    ),
                )
            return httpx.Response(200, json=make_next_offset_page(entries=[]))

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            results = await client.get_all_pages_next_url("/v3/events")
            assert len(results) == 3
            assert [r["id"] for r in results] == ["e1", "e2", "e3"]
            assert call_count == 2
        finally:
            await client._http.aclose()


# ===================================================================
# Configuration Tests
# ===================================================================


class TestConfiguration:
    """Test that configuration is properly read from settings."""

    def test_default_base_url_from_settings(self):
        """Base URL defaults to settings.gfw.base_url."""
        client = GFWClient(api_token="test")
        assert "globalfishingwatch.org" in client._base_url

    def test_custom_base_url(self):
        """Base URL can be overridden via constructor."""
        client = GFWClient(
            api_token="test",
            base_url="https://custom.api.test/v3",
        )
        assert client._base_url == "https://custom.api.test/v3"

    def test_trailing_slash_stripped(self):
        """Trailing slash on base URL is stripped."""
        client = GFWClient(
            api_token="test",
            base_url="https://custom.api.test/",
        )
        assert client._base_url == "https://custom.api.test"

    def test_api_token_from_settings(self):
        """API token defaults to settings.gfw_api_token."""
        client = GFWClient()
        assert client._api_token == settings.gfw_api_token

    def test_custom_api_token(self):
        """API token can be overridden via constructor."""
        client = GFWClient(api_token="my-custom-token")
        assert client._api_token == "my-custom-token"


# ===================================================================
# Context Manager Tests
# ===================================================================


class TestContextManager:
    """Test async context manager lifecycle."""

    @pytest.mark.asyncio
    async def test_context_manager_creates_and_closes_http_client(self):
        """HTTP client is created on enter and closed on exit."""
        client = GFWClient(
            api_token="test",
            base_url="https://mock-gfw.test",
        )
        assert client._http is None

        async with client:
            assert client._http is not None
            assert isinstance(client._http, httpx.AsyncClient)

        assert client._http is None

    @pytest.mark.asyncio
    async def test_post_method(self):
        """POST requests work correctly."""
        received_body = None

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal received_body
            if request.url.path == "/auth/token":
                return httpx.Response(200, json=make_token_response())
            received_body = json.loads(request.content)
            return httpx.Response(200, json={"created": True})

        transport = httpx.MockTransport(mock_handler)

        client = GFWClient(
            api_token="test-api-token",
            base_url="https://mock-gfw.test",
            rate_limit_per_second=100,
        )
        client._http = httpx.AsyncClient(
            transport=transport, base_url="https://mock-gfw.test"
        )

        try:
            result = await client.post(
                "/v3/vessels/search",
                json_body={"query": "MMSI 123456789"},
            )
            assert result == {"created": True}
            assert received_body == {"query": "MMSI 123456789"}
        finally:
            await client._http.aclose()
