"""Shared pytest fixtures.

Tests never hit the real upstream. We build an `httpx.AsyncClient` on top
of `httpx.MockTransport` so route handlers and the service layer see a
perfectly normal client — but requests are served by our in-process
handler. This gives us deterministic, offline tests with realistic HTTP
semantics (status codes, headers, raise_for_status, etc.).
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

import httpx
import pytest
import pytest_asyncio

from app.main import app
from app.services.orbital_client import OrbitalClient


def _make_mock_transport(
    messages: List[dict],
    reports: Dict[int, Optional[dict]],
) -> httpx.MockTransport:
    """Return a MockTransport serving the two upstream endpoints.

    `reports` maps report_id -> payload. Use `None` to simulate a 404
    (the documented fallback path). Missing IDs also 404.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/messages/current-period"):
            return httpx.Response(200, json=messages)
        if "/reports/" in path:
            rid = int(path.rsplit("/", 1)[-1])
            if rid not in reports or reports[rid] is None:
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(200, json=reports[rid])
        return httpx.Response(500, json={"detail": "unexpected route"})

    return httpx.MockTransport(handler)


@pytest.fixture
def make_client() -> Callable[[List[dict], Dict[int, Optional[dict]]], OrbitalClient]:
    """Factory fixture that builds an `OrbitalClient` around a MockTransport."""

    def _factory(messages: List[dict], reports: Dict[int, Optional[dict]]) -> OrbitalClient:
        transport = _make_mock_transport(messages, reports)
        http_client = httpx.AsyncClient(transport=transport, base_url="http://mocked")
        return OrbitalClient(client=http_client)

    return _factory


@pytest_asyncio.fixture
async def api_client(monkeypatch):
    """An `httpx.AsyncClient` pointed at the FastAPI app in-process.

    Tests that need a specific upstream response should override
    `app.state.http_client` with a MockTransport-backed client inside the
    test — this fixture only stands up the app itself.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def install_mock_upstream(
    messages: List[dict], reports: Dict[int, Optional[dict]]
) -> httpx.AsyncClient:
    """Swap the app's shared HTTP client for a MockTransport-backed one.

    Returns the installed client so tests can inspect request history if
    needed. The app's lifespan will still try to close its own client on
    shutdown; since we replaced `app.state.http_client`, we close the
    original here to keep the event loop tidy.
    """
    transport = _make_mock_transport(messages, reports)
    mocked = httpx.AsyncClient(transport=transport, base_url="http://mocked")
    app.state.http_client = mocked
    return mocked
