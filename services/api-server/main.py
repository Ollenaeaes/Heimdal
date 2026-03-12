"""Heimdal API server entry point.

Creates a FastAPI application with lifespan management for database
and Redis connections.  Run with ``uvicorn main:app`` or directly
via ``python main.py``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.config import settings
from shared.db.connection import get_engine, dispose_engine

logger = logging.getLogger("api-server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of database and Redis connections."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Startup: initialise the async engine (validates connectivity)
    engine = get_engine()
    logger.info("Database engine initialised: %s", engine.url.database)

    # Startup: connect to Redis
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    app.state.redis = redis_client
    logger.info("Redis connected: %s", settings.redis_url)

    yield

    # Shutdown: close Redis
    await redis_client.close()
    logger.info("Redis connection closed")

    # Shutdown: dispose database engine
    await dispose_engine()
    logger.info("Database engine disposed")


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title="Heimdal API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------
    from routes.health import router as health_router
    from routes.vessels import router as vessels_router
    from routes.anomalies import router as anomalies_router
    from routes.sar import router as sar_router
    from routes.gfw import router as gfw_router
    from routes.watchlist import router as watchlist_router
    from routes.enrichment import router as enrichment_router
    from routes.ws_alerts import router as ws_alerts_router
    from routes.ws_positions import router as ws_positions_router

    app.include_router(health_router)
    app.include_router(vessels_router)
    app.include_router(anomalies_router)
    app.include_router(sar_router)
    app.include_router(gfw_router)
    app.include_router(watchlist_router)
    app.include_router(enrichment_router)
    app.include_router(ws_alerts_router)
    app.include_router(ws_positions_router)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
