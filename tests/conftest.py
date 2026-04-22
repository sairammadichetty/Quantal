"""Shared pytest fixtures.

Tests never hit the real upstream. We build an `httpx.AsyncClient` on top
of `httpx.MockTransport` so route handlers and the service layer see a
perfectly normal client — but requests are served by our in-process
handler. This gives us deterministic, offline tests with realistic HTTP
semantics (status codes, headers, raise_for_status, etc.).
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import pytest_asyncio

from app.core.config import settings
from app.main import app
from app.services.orbital_client import OrbitalClient


def _make_mock_transport(
    messages: list[dict],
    reports: dict[int, dict | None],
) -> httpx.MockTransport:
    """Return a MockTransport serving the two upstream endpoints.

    Route matching is driven by the current `settings` values rather than
    hardcoded literals, so overriding `ORBITAL_MESSAGES_PATH` or
    `ORBITAL_REPORT_PATH_TEMPLATE` in a test automatically re-targets the
    mock. `reports` maps report_id -> payload; use `None` to simulate a
    documented 404 fallback. Unknown IDs also 404.
    """
    # Pre-compute the expected paths once per transport so the handler stays
    # cheap and obvious.
    messages_path = settings.ORBITAL_MESSAGES_PATH
    report_template = settings.ORBITAL_REPORT_PATH_TEMPLATE
    # Split on the placeholder so we can pattern-match without regex.
    report_prefix, report_suffix = report_template.split("{report_id}", 1)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == messages_path:
            return httpx.Response(200, json=messages)
        if path.startswith(report_prefix) and path.endswith(report_suffix):
            rid_str = path[len(report_prefix) : len(path) - len(report_suffix) or None]
            try:
                rid = int(rid_str)
            except ValueError:
                return httpx.Response(400, json={"detail": "bad report id"})
            if rid not in reports or reports[rid] is None:
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(200, json=reports[rid])
        return httpx.Response(500, json={"detail": f"unexpected route: {path}"})

    return httpx.MockTransport(handler)


@pytest.fixture
def make_client() -> Callable[[list[dict], dict[int, dict | None]], OrbitalClient]:
    """Factory fixture that builds an `OrbitalClient` around a MockTransport."""

    def _factory(messages: list[dict], reports: dict[int, dict | None]) -> OrbitalClient:
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
    messages: list[dict], reports: dict[int, dict | None]
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
