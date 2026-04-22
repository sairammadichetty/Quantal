"""Thin async HTTP client for the Orbital Copilot upstream services.

This module owns HTTP concerns only: base URL, timeouts, and the
documented "404 means fall back to text calculation" semantic for the
reports endpoint. It returns validated Pydantic models so the service
layer never touches raw dicts.

Keeping the surface narrow makes this trivial to mock in tests by
injecting an `httpx.AsyncClient` backed by `httpx.MockTransport`.
"""

from __future__ import annotations

from typing import List, Optional

import httpx

from app.core.config import settings
from app.schemas.upstream import Message, Report


class OrbitalClient:
    """Async client for the two upstream endpoints described in the brief."""

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url=settings.ORBITAL_BASE_URL,
            timeout=settings.ORBITAL_HTTP_TIMEOUT_SECONDS,
        )

    async def get_messages(self) -> List[Message]:
        """Return all messages for the current billing period.

        Any non-2xx is raised: there is no sensible fallback if we cannot
        enumerate messages. Upstream payload shape is validated by Pydantic
        so a contract change surfaces with a clear error here rather than a
        `KeyError` deep inside the credit engine.
        """
        response = await self.client.get("/messages/current-period")
        response.raise_for_status()
        payload = response.json()
        # Defensive against a `{"messages": [...]}` shape; the brief documents
        # a bare list but we accept either.
        raw = payload["messages"] if isinstance(payload, dict) and "messages" in payload else payload
        return [Message.model_validate(item) for item in raw]

    async def get_report(self, report_id: int) -> Optional[Report]:
        """Return the report metadata, or `None` if the upstream 404s.

        404 is a documented fallback signal per the brief, not an error, so
        we swallow it and return None. Any other non-2xx is raised so a real
        upstream outage isn't silently masked as a text-calc fallback.
        """
        response = await self.client.get(f"/reports/{report_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return Report.model_validate(response.json())

    async def close(self) -> None:
        """Close the underlying HTTP client iff we created it.

        When a caller injects their own client (FastAPI lifespan, tests), we
        leave lifecycle management to them.
        """
        if self._owns_client:
            await self.client.aclose()
