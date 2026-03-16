"""Async SQLAlchemy engine and session factory (singleton)."""

from __future__ import annotations

import logging
import time

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.config import settings

logger = logging.getLogger("shared.db")

# Module-level singletons
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

# Thresholds (in milliseconds)
SLOW_QUERY_THRESHOLD_MS = 500
VERY_SLOW_QUERY_THRESHOLD_MS = 5000


def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Store the query start time on the connection info dict."""
    conn.info["query_start_time"] = time.monotonic()


def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Log query duration at appropriate level based on elapsed time."""
    start = conn.info.pop("query_start_time", None)
    if start is None:
        return
    duration_ms = (time.monotonic() - start) * 1000
    query_snippet = (statement[:200] if statement else "")
    extra = {
        "duration_ms": round(duration_ms, 2),
        "query": query_snippet,
        "service": "shared.db",
    }

    if duration_ms > VERY_SLOW_QUERY_THRESHOLD_MS:
        logger.error(
            "very_slow_query",
            extra={**extra, "slow_query": True},
        )
    elif duration_ms > SLOW_QUERY_THRESHOLD_MS:
        logger.warning(
            "slow_query",
            extra={**extra, "slow_query": True},
        )
    else:
        logger.debug("query_complete", extra=extra)


def _on_checkout(dbapi_conn, connection_record, connection_proxy):
    """Log when a connection is checked out from the pool."""
    logger.debug("pool_checkout", extra={"service": "shared.db"})


def _on_checkin(dbapi_conn, connection_record):
    """Log when a connection is returned to the pool."""
    logger.debug("pool_checkin", extra={"service": "shared.db"})


def _on_checkout_failed(exception, pool, _ignored):
    """Log pool exhaustion when checkout fails due to overflow/timeout."""
    logger.error(
        "pool_exhausted",
        extra={"pool_exhausted": True, "service": "shared.db", "error": str(exception)},
    )


def _attach_engine_listeners(engine: AsyncEngine) -> None:
    """Attach SQLAlchemy event listeners to the sync engine underlying the async engine."""
    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _before_cursor_execute)
    event.listen(sync_engine, "after_cursor_execute", _after_cursor_execute)

    pool = sync_engine.pool
    event.listen(pool, "checkout", _on_checkout)
    event.listen(pool, "checkin", _on_checkin)


def get_engine() -> AsyncEngine:
    """Return the singleton async engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url.get_secret_value(),
            pool_size=5,
            max_overflow=3,
            pool_pre_ping=True,
            echo=False,
        )
        _attach_engine_listeners(_engine)
    return _engine


def get_session() -> async_sessionmaker[AsyncSession]:
    """Return the singleton async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def dispose_engine() -> None:
    """Dispose the engine, closing all pooled connections."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
