"""Global Fishing Watch API client with rate limiting, pagination, and retries.

Uses the GFW API token directly as a Bearer token on every request.
Enforces configurable rate limits, retries on transient errors, and
handles paginated responses automatically.  Tracks daily/monthly API
usage against GFW quota limits (persisted to a JSON file on disk).
"""

from __future__ import annotations

import asyncio
import json as json_mod
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
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


class GFWQuotaExceeded(Exception):
    """Raised when the daily or monthly API quota would be exceeded."""


class _QuotaTracker:
    """Tracks daily and monthly GFW API call counts in a persistent JSON file.

    File format::

        {
          "daily": {"date": "2026-03-16", "count": 123},
          "monthly": {"month": "2026-03", "count": 4567}
        }
    """

    def __init__(
        self,
        path: str,
        daily_limit: int,
        monthly_limit: int,
    ):
        self._path = Path(path)
        self._daily_limit = daily_limit
        self._monthly_limit = monthly_limit
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            return json_mod.loads(self._path.read_text())
        except (FileNotFoundError, json_mod.JSONDecodeError, OSError):
            return {"daily": {"date": "", "count": 0}, "monthly": {"month": "", "count": 0}}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json_mod.dumps(self._data))
        except OSError:
            logger.warning("Failed to persist GFW quota file to %s", self._path)

    def _roll_windows(self) -> None:
        """Reset counters if the date/month has changed."""
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        month = now.strftime("%Y-%m")

        if self._data["daily"].get("date") != today:
            self._data["daily"] = {"date": today, "count": 0}
        if self._data["monthly"].get("month") != month:
            self._data["monthly"] = {"month": month, "count": 0}

    def check_quota(self) -> None:
        """Raise GFWQuotaExceeded if we'd exceed the daily or monthly limit."""
        self._roll_windows()
        d = self._data["daily"]["count"]
        m = self._data["monthly"]["count"]
        if d >= self._daily_limit:
            raise GFWQuotaExceeded(
                f"GFW daily quota reached: {d}/{self._daily_limit} requests"
            )
        if m >= self._monthly_limit:
            raise GFWQuotaExceeded(
                f"GFW monthly quota reached: {m}/{self._monthly_limit} requests"
            )

    def record_call(self) -> None:
        """Increment both daily and monthly counters and persist."""
        self._roll_windows()
        self._data["daily"]["count"] += 1
        self._data["monthly"]["count"] += 1
        self._save()

    def get_usage(self) -> dict[str, Any]:
        """Return current usage stats."""
        self._roll_windows()
        return {
            "daily_calls": self._data["daily"]["count"],
            "daily_limit": self._daily_limit,
            "monthly_calls": self._data["monthly"]["count"],
            "monthly_limit": self._monthly_limit,
        }


class GFWClient:
    """Async client for the Global Fishing Watch API.

    Uses the API token directly as a Bearer token. Handles rate limiting,
    retry with exponential backoff, and pagination.

    Usage::

        async with GFWClient() as client:
            events = await client.get("/events", params={"limit": 10})
    """

    # Thresholds for slow API call warnings (milliseconds)
    SLOW_CALL_WARNING_MS = 5000
    SLOW_CALL_ERROR_MS = 30000

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

        # API call statistics (reset per enrichment cycle)
        self._call_count: int = 0
        self._total_call_duration_ms: float = 0.0
        self._retry_count: int = 0

        # Persistent daily/monthly quota tracker
        self._quota = _QuotaTracker(
            path=settings.gfw.quota_file_path,
            daily_limit=settings.gfw.daily_request_limit,
            monthly_limit=settings.gfw.monthly_request_limit,
        )

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
    # API call statistics
    # ------------------------------------------------------------------

    def reset_stats(self) -> None:
        """Reset API call statistics. Call before each enrichment cycle."""
        self._call_count = 0
        self._total_call_duration_ms = 0.0
        self._retry_count = 0

    def get_stats(self) -> dict[str, Any]:
        """Return API call statistics for the current cycle."""
        avg_ms = (
            self._total_call_duration_ms / self._call_count
            if self._call_count > 0
            else 0.0
        )
        stats = {
            "api_calls_made": self._call_count,
            "total_call_duration_ms": round(self._total_call_duration_ms, 1),
            "avg_call_duration_ms": round(avg_ms, 1),
            "rate_limit_retries": self._retry_count,
        }
        stats.update(self._quota.get_usage())
        return stats

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

    def _log_api_call(
        self, method: str, path: str, status_code: int, duration_ms: float
    ) -> None:
        """Log an API call with duration and threshold-based severity."""
        log_extra = {
            "duration_ms": round(duration_ms, 1),
            "url": path,
            "status_code": status_code,
            "method": method,
        }

        if duration_ms > self.SLOW_CALL_ERROR_MS:
            logger.error(
                "GFW API call %s %s took %.0fms (status %d)",
                method,
                path,
                duration_ms,
                status_code,
                extra=log_extra,
            )
        elif duration_ms > self.SLOW_CALL_WARNING_MS:
            logger.warning(
                "GFW API call %s %s took %.0fms (status %d)",
                method,
                path,
                duration_ms,
                status_code,
                extra={**log_extra, "slow_api_call": True},
            )
        else:
            logger.debug(
                "GFW API call %s %s completed in %.0fms (status %d)",
                method,
                path,
                duration_ms,
                status_code,
                extra=log_extra,
            )

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

        # Check daily/monthly quota before making the request
        self._quota.check_quota()

        backoff = INITIAL_BACKOFF

        for attempt in range(MAX_RETRIES + 1):
            await self._wait_for_rate_limit()

            try:
                call_start = time.monotonic()
                response = await self._http.request(
                    method,
                    path,
                    params=params,
                    json=json_body,
                    headers={"Authorization": f"Bearer {self._api_token}"},
                )
                duration_ms = (time.monotonic() - call_start) * 1000

                # Track stats
                self._call_count += 1
                self._total_call_duration_ms += duration_ms
                self._quota.record_call()

                if response.status_code in RETRYABLE_STATUS_CODES:
                    if attempt < MAX_RETRIES:
                        retry_after = response.headers.get("Retry-After")
                        wait = float(retry_after) if retry_after else backoff
                        self._retry_count += 1
                        logger.warning(
                            "GFW API returned %d on attempt %d/%d for %s %s, retrying in %.1fs",
                            response.status_code,
                            attempt + 1,
                            MAX_RETRIES + 1,
                            method,
                            path,
                            wait,
                            extra={
                                "duration_ms": round(duration_ms, 1),
                                "url": path,
                                "status_code": response.status_code,
                                "method": method,
                                "retry_attempt": attempt + 1,
                                "retry_reason": f"HTTP {response.status_code}",
                            },
                        )
                        await asyncio.sleep(wait)
                        backoff *= 2
                        continue
                    # Final attempt also failed — log before raising
                    self._log_api_call(method, path, response.status_code, duration_ms)
                    raise GFWAPIError(
                        f"GFW API request failed after {MAX_RETRIES + 1} attempts: "
                        f"{response.status_code} {response.text}",
                        status_code=response.status_code,
                    )

                # Successful response — log with duration and threshold checks
                self._log_api_call(method, path, response.status_code, duration_ms)

                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                raise GFWAPIError(
                    f"GFW API error: {e.response.status_code} {e.response.text}",
                    status_code=e.response.status_code,
                ) from e
            except httpx.HTTPError as e:
                duration_ms = (time.monotonic() - call_start) * 1000
                self._call_count += 1
                self._total_call_duration_ms += duration_ms
                if attempt < MAX_RETRIES:
                    self._retry_count += 1
                    logger.warning(
                        "GFW API connection error on attempt %d/%d: %s, retrying in %.1fs",
                        attempt + 1,
                        MAX_RETRIES + 1,
                        e,
                        backoff,
                        extra={
                            "duration_ms": round(duration_ms, 1),
                            "url": path,
                            "method": method,
                            "retry_attempt": attempt + 1,
                            "retry_reason": str(type(e).__name__),
                        },
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
