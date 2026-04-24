"""Shared pytest fixtures.

Tests never hit the real upstream — we wrap httpx.MockTransport around the
same AsyncClient the app uses, so route handlers and the service layer
see a normal client but requests are served in-process.
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
    """MockTransport serving the two upstream endpoints.

    Route matching uses the current settings so tests that override
    ORBITAL_MESSAGES_PATH / ORBITAL_REPORT_PATH_TEMPLATE automatically
    re-target the mock. A report value of None simulates the 404 fallback.
    """
    messages_path = settings.ORBITAL_MESSAGES_PATH
    report_template = settings.ORBITAL_REPORT_PATH_TEMPLATE
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
    def _factory(messages: list[dict], reports: dict[int, dict | None]) -> OrbitalClient:
        transport = _make_mock_transport(messages, reports)
        http_client = httpx.AsyncClient(transport=transport, base_url="http://mocked")
        return OrbitalClient(client=http_client)

    return _factory


@pytest_asyncio.fixture
async def api_client(monkeypatch):
    """AsyncClient pointed at the FastAPI app in-process.

    Tests that need a specific upstream response call install_mock_upstream
    to swap app.state.http_client for a MockTransport-backed one.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def install_mock_upstream(
    messages: list[dict], reports: dict[int, dict | None]
) -> httpx.AsyncClient:
    """Swap the app's shared HTTP client for a MockTransport-backed one."""
    transport = _make_mock_transport(messages, reports)
    mocked = httpx.AsyncClient(transport=transport, base_url="http://mocked")
    app.state.http_client = mocked
    return mocked
