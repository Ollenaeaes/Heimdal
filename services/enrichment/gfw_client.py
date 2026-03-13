"""Global Fishing Watch API client with rate limiting, pagination, and retries.

Uses the GFW API token directly as a Bearer token on every request.
Enforces configurable rate limits, retries on transient errors, and
handles paginated responses automatically.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from typing import Any

import httpx

sys.path.insert(0, "/app")

from shared.config import settings

logger = logging.getLogger("enrichment.gfw_client")

# HTTP status codes that trigger retries
RETRYABLE_STATUS_CODES = {429, 500, 502, 503}

# Maximum number of retry attempts for transient failures
MAX_RETRIES = 3

# Initial backoff delay in seconds (doubles on each retry)
INITIAL_BACKOFF = 1.0


class GFWAuthError(Exception):
    """Raised when authentication with GFW API fails."""


class GFWAPIError(Exception):
    """Raised when a GFW API request fails after all retries."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class GFWClient:
    """Async client for the Global Fishing Watch API.

    Uses the API token directly as a Bearer token. Handles rate limiting,
    retry with exponential backoff, and pagination.

    Usage::

        async with GFWClient() as client:
            events = await client.get("/events", params={"limit": 10})
    """

    def __init__(
        self,
        api_token: str | None = None,
        base_url: str | None = None,
        rate_limit_per_second: int | None = None,
    ):
        self._api_token = api_token or settings.gfw_api_token
        self._base_url = (base_url or settings.gfw.base_url).rstrip("/")
        self._rate_limit = rate_limit_per_second or settings.gfw.rate_limit_per_second

        # Rate limiting via a semaphore + delay
        self._semaphore = asyncio.Semaphore(self._rate_limit)
        self._request_interval = 1.0 / self._rate_limit
        self._last_request_time: float = 0.0
        self._rate_lock = asyncio.Lock()

        # HTTP client (created on __aenter__)
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> GFWClient:
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    async def _wait_for_rate_limit(self) -> None:
        """Enforce the configured rate limit using a token bucket approach."""
        async with self._rate_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._request_interval:
                await asyncio.sleep(self._request_interval - elapsed)
            self._last_request_time = time.monotonic()

    # ------------------------------------------------------------------
    # Request execution with retries
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Execute a single HTTP request with auth, rate limiting, and retries."""
        if not self._http:
            raise RuntimeError("Client not initialized. Use 'async with GFWClient() as client:'")

        backoff = INITIAL_BACKOFF

        for attempt in range(MAX_RETRIES + 1):
            await self._wait_for_rate_limit()

            try:
                response = await self._http.request(
                    method,
                    path,
                    params=params,
                    json=json_body,
                    headers={"Authorization": f"Bearer {self._api_token}"},
                )

                if response.status_code in RETRYABLE_STATUS_CODES:
                    if attempt < MAX_RETRIES:
                        retry_after = response.headers.get("Retry-After")
                        wait = float(retry_after) if retry_after else backoff
                        logger.warning(
                            "GFW API returned %d on attempt %d/%d for %s %s, retrying in %.1fs",
                            response.status_code,
                            attempt + 1,
                            MAX_RETRIES + 1,
                            method,
                            path,
                            wait,
                        )
                        await asyncio.sleep(wait)
                        backoff *= 2
                        continue
                    raise GFWAPIError(
                        f"GFW API request failed after {MAX_RETRIES + 1} attempts: "
                        f"{response.status_code} {response.text}",
                        status_code=response.status_code,
                    )

                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                raise GFWAPIError(
                    f"GFW API error: {e.response.status_code} {e.response.text}",
                    status_code=e.response.status_code,
                ) from e
            except httpx.HTTPError as e:
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "GFW API connection error on attempt %d/%d: %s, retrying in %.1fs",
                        attempt + 1,
                        MAX_RETRIES + 1,
                        e,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                raise GFWAPIError(
                    f"GFW API request failed after {MAX_RETRIES + 1} attempts: {e}"
                ) from e

        # Should not reach here, but just in case
        raise GFWAPIError("Unexpected retry loop exit")

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """GET a single (non-paginated) endpoint and return parsed JSON."""
        response = await self._request("GET", path, params=params)
        return response.json()

    async def post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST to an endpoint and return parsed JSON."""
        response = await self._request("POST", path, params=params, json_body=json_body)
        return response.json()

    async def get_all_pages(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        results_key: str = "entries",
        limit_param: str = "limit",
        offset_param: str = "offset",
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch all pages from a paginated GFW endpoint.

        The GFW Events API uses offset-based pagination with ``limit``
        and ``offset`` query parameters.  Responses include a ``total``
        field and a list of results under ``results_key`` (default:
        ``"entries"``).

        Returns a flat list of all result items across all pages.
        """
        all_results: list[dict[str, Any]] = []
        offset = 0
        request_params = dict(params or {})

        while True:
            request_params[limit_param] = page_size
            request_params[offset_param] = offset

            response = await self._request("GET", path, params=request_params)
            data = response.json()

            entries = data.get(results_key, [])
            all_results.extend(entries)

            total = data.get("total", 0)
            offset += len(entries)

            if not entries or offset >= total:
                break

        return all_results

    async def get_all_pages_next_url(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        results_key: str = "entries",
    ) -> list[dict[str, Any]]:
        """Fetch all pages using ``nextOffset`` cursor from the GFW API.

        Some GFW endpoints use a ``nextOffset`` field in the response
        instead of standard offset-based pagination. This method follows
        those cursors until exhausted.

        Returns a flat list of all result items across all pages.
        """
        all_results: list[dict[str, Any]] = []
        request_params = dict(params or {})

        while True:
            response = await self._request("GET", path, params=request_params)
            data = response.json()

            entries = data.get(results_key, [])
            all_results.extend(entries)

            next_offset = data.get("nextOffset")
            if not entries or next_offset is None:
                break

            request_params["offset"] = next_offset

        return all_results
