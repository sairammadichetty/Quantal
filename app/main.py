"""FastAPI application entrypoint.

This file is deliberately small: it is the *composition root* of the app.
It:

1. Configures logging.
2. Manages the lifecycle of the shared `httpx.AsyncClient` (connection
   pooling, single TLS session) via FastAPI's `lifespan` context manager.
3. Registers routers and exception handlers.

Business logic lives in `app.services.*` and route handlers in
`app.api.v1.endpoints`.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.v1.endpoints import router as v1_router
from app.core.config import settings

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Own the single shared httpx client for the app's lifetime.

    Creating the client per-request (as the original implementation did)
    forces a new TCP + TLS handshake every time and wastes ~hundreds of ms
    per call. A shared client gives us connection pooling for free.
    """
    client = httpx.AsyncClient(
        base_url=settings.ORBITAL_BASE_URL,
        timeout=settings.ORBITAL_HTTP_TIMEOUT_SECONDS,
    )
    app.state.http_client = client
    logger.info("HTTP client started (base_url=%s)", settings.ORBITAL_BASE_URL)
    try:
        yield
    finally:
        await client.aclose()
        logger.info("HTTP client closed")


app = FastAPI(
    title=settings.APP_NAME,
    description="Calculates credit consumption for Orbital Copilot messages.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(v1_router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    """Lightweight liveness probe for container orchestrators."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
