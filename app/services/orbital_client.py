"""Async HTTP client for the Orbital Copilot upstream."""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.schemas.upstream import Message, Report


class OrbitalClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url=settings.ORBITAL_BASE_URL,
            timeout=settings.ORBITAL_HTTP_TIMEOUT_SECONDS,
        )

    async def get_messages(self) -> list[Message]:
        response = await self.client.get(settings.ORBITAL_MESSAGES_PATH)
        response.raise_for_status()
        payload = response.json()
        # The brief documents a bare list, but some deployments wrap it in
        # {"messages": [...]} — accept either.
        raw = (
            payload["messages"] if isinstance(payload, dict) and "messages" in payload else payload
        )
        return [Message.model_validate(item) for item in raw]

    async def get_report(self, report_id: int) -> Report | None:
        """Return report metadata, or None when the upstream 404s.

        A 404 is the documented fallback signal (use text calc instead);
        any other non-2xx is raised so a real outage isn't masked.
        """
        path = settings.ORBITAL_REPORT_PATH_TEMPLATE.format(report_id=report_id)
        response = await self.client.get(path)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return Report.model_validate(response.json())

    async def close(self) -> None:
        # Only close clients we created ourselves; an injected client
        # belongs to the caller (FastAPI lifespan, tests).
        if self._owns_client:
            await self.client.aclose()
