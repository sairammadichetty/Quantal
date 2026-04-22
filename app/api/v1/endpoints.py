"""HTTP routes for the v1 API.

The route is intentionally thin: it delegates to `build_usage_response`
and catches upstream-specific failures so we can map them to appropriate
HTTP status codes. Anything unexpected is re-raised to be handled by the
global exception handler registered in `main.py`.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.usage import UsageResponse
from app.services.orbital_client import OrbitalClient
from app.services.usage_service import build_usage_response

logger = logging.getLogger(__name__)

router = APIRouter()


def get_orbital_client(request: Request) -> OrbitalClient:
    """FastAPI dependency that yields a client wrapping the shared httpx pool.

    The underlying `httpx.AsyncClient` is created once in the lifespan and
    reused across requests; passing it into `OrbitalClient(client=...)`
    prevents the client from closing it when the request ends.
    """
    return OrbitalClient(client=request.app.state.http_client)


@router.get(
    "/usage",
    response_model=UsageResponse,
    # Critical: honour the contract that `report_name` is omitted, not `null`.
    response_model_exclude_none=True,
    summary="Return usage for the current billing period",
)
async def get_usage(client: OrbitalClient = Depends(get_orbital_client)) -> UsageResponse:
    try:
        return await build_usage_response(client)
    except httpx.HTTPStatusError as exc:
        # Upstream returned a non-2xx that we chose not to handle (e.g. 5xx
        # on the messages endpoint). Map to 502 so callers can distinguish
        # "our bug" from "dependency is unhappy".
        logger.exception("Upstream returned an error status")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream service error",
        ) from exc
    except httpx.HTTPError as exc:
        # Network-level failure (timeout, DNS, connection reset, etc.).
        logger.exception("Upstream network error")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Upstream service unavailable",
        ) from exc
