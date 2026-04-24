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
    # Reuse the shared httpx client owned by the app's lifespan so we're
    # not doing a TCP + TLS handshake on every request.
    return OrbitalClient(client=request.app.state.http_client)


@router.get(
    "/usage",
    response_model=UsageResponse,
    # report_name must be absent (not null) when no report is attached.
    response_model_exclude_none=True,
    summary="Return usage for the current billing period",
)
async def get_usage(client: OrbitalClient = Depends(get_orbital_client)) -> UsageResponse:
    try:
        return await build_usage_response(client)
    except httpx.HTTPStatusError as exc:
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
