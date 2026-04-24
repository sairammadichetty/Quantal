"""End-to-end tests for /usage — full ASGI stack, mocked upstream."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import install_mock_upstream


@pytest.mark.asyncio
async def test_usage_endpoint_returns_expected_shape(api_client: httpx.AsyncClient):
    install_mock_upstream(
        messages=[
            {"id": 1, "timestamp": "2024-04-29T02:08:29.375Z", "text": "Hi", "report_id": None},
        ],
        reports={},
    )

    response = await api_client.get("/usage")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"usage"}
    assert isinstance(body["usage"], list)
    item = body["usage"][0]
    # Required fields per the contract: message_id, timestamp, credits_used.
    assert item["message_id"] == 1
    assert item["timestamp"] == "2024-04-29T02:08:29.375Z"
    assert isinstance(item["credits_used"], int | float)
    # Guard against the old field names sneaking back in.
    assert "id" not in item
    assert "credits" not in item


@pytest.mark.asyncio
async def test_report_name_is_omitted_when_no_report(api_client: httpx.AsyncClient):
    # The key must be absent from JSON, not present with null.
    install_mock_upstream(
        messages=[
            {"id": 10, "timestamp": "2024-04-29T02:08:29Z", "text": "Just asking a question"},
        ],
        reports={},
    )
    response = await api_client.get("/usage")
    item = response.json()["usage"][0]
    assert "report_name" not in item

    # Belt-and-braces: check the raw bytes too, in case someone drops
    # response_model_exclude_none in future.
    raw = response.text
    assert "report_name" not in raw
    assert '"report_name":null' not in raw.replace(" ", "")


@pytest.mark.asyncio
async def test_report_name_and_fixed_cost_when_report_exists(api_client: httpx.AsyncClient):
    install_mock_upstream(
        messages=[
            {
                "id": 20,
                "timestamp": "2024-04-29T02:10:00Z",
                "text": "ignored when report_id present",
                "report_id": 999,
            },
        ],
        reports={999: {"name": "Short Lease Report", "credit_cost": 79}},
    )
    response = await api_client.get("/usage")
    item = response.json()["usage"][0]
    # Fixed report cost, not the text-based calc.
    assert item["credits_used"] == 79
    assert item["report_name"] == "Short Lease Report"


@pytest.mark.asyncio
async def test_404_report_falls_back_to_text_calc(api_client: httpx.AsyncClient):
    # report_id present, but /reports/{id} 404s -> text calc. "aba" is a
    # palindrome and comes out at 2.0 after the floor+double.
    install_mock_upstream(
        messages=[
            {
                "id": 30,
                "timestamp": "2024-04-29T02:11:00Z",
                "text": "aba",  # expected text-calc result: 2.0 (palindrome)
                "report_id": 404,
            },
        ],
        reports={404: None},  # installs a 404 for this id
    )
    response = await api_client.get("/usage")
    item = response.json()["usage"][0]
    assert item["credits_used"] == 2.0
    assert "report_name" not in item


@pytest.mark.asyncio
async def test_duplicate_report_ids_are_fetched_once(api_client: httpx.AsyncClient, monkeypatch):
    # Three messages, one report_id -> one upstream call.
    call_counter = {"hits": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages/current-period"):
            return httpx.Response(
                200,
                json=[
                    {"id": 1, "timestamp": "t1", "text": "", "report_id": 7},
                    {"id": 2, "timestamp": "t2", "text": "", "report_id": 7},
                    {"id": 3, "timestamp": "t3", "text": "", "report_id": 7},
                ],
            )
        if "/reports/" in request.url.path:
            call_counter["hits"] += 1
            return httpx.Response(200, json={"name": "Same Report", "credit_cost": 10})
        return httpx.Response(500)

    from app.main import app

    app.state.http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://mocked"
    )

    response = await api_client.get("/usage")
    body = response.json()

    assert response.status_code == 200
    assert [item["credits_used"] for item in body["usage"]] == [10, 10, 10]
    assert all(item["report_name"] == "Same Report" for item in body["usage"])
    # Deduplication: only one upstream /reports/7 call for three messages.
    assert call_counter["hits"] == 1


@pytest.mark.asyncio
async def test_upstream_5xx_on_messages_returns_502(api_client: httpx.AsyncClient):
    # If the messages endpoint itself fails we cannot proceed, so surface
    # a 502 Bad Gateway rather than a 500 (which would suggest our bug).
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    from app.main import app

    app.state.http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://mocked"
    )

    response = await api_client.get("/usage")
    assert response.status_code == 502


@pytest.mark.asyncio
async def test_contract_field_names_and_presence(api_client: httpx.AsyncClient):
    """Lock the wire contract: exact field names, nothing extra."""
    install_mock_upstream(
        messages=[
            {"id": 1, "timestamp": "t1", "text": "Hi", "report_id": None},
            {"id": 2, "timestamp": "t2", "text": "ignored", "report_id": 42},
        ],
        reports={42: {"name": "Lease Report", "credit_cost": 79}},
    )
    body = (await api_client.get("/usage")).json()

    assert list(body.keys()) == ["usage"]

    no_report_item = body["usage"][0]
    assert set(no_report_item.keys()) == {"message_id", "timestamp", "credits_used"}

    report_item = body["usage"][1]
    assert set(report_item.keys()) == {"message_id", "timestamp", "report_name", "credits_used"}


@pytest.mark.asyncio
async def test_healthz_liveness_probe(api_client: httpx.AsyncClient):
    response = await api_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_messages_path_is_configurable(
    monkeypatch: pytest.MonkeyPatch, api_client: httpx.AsyncClient
):
    """Overriding ORBITAL_MESSAGES_PATH actually re-targets the upstream."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ORBITAL_MESSAGES_PATH", "/messages/2025-Q1")

    install_mock_upstream(
        messages=[
            {"id": 99, "timestamp": "ts", "text": "Hi", "report_id": None},
        ],
        reports={},
    )
    response = await api_client.get("/usage")

    assert response.status_code == 200
    body = response.json()
    assert body["usage"][0]["message_id"] == 99


@pytest.mark.asyncio
async def test_report_template_is_configurable(
    monkeypatch: pytest.MonkeyPatch, api_client: httpx.AsyncClient
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ORBITAL_REPORT_PATH_TEMPLATE", "/v2/reports/{report_id}/detail")

    install_mock_upstream(
        messages=[
            {"id": 7, "timestamp": "ts", "text": "ignored", "report_id": 42},
        ],
        reports={42: {"name": "Alt-Path Report", "credit_cost": 12.5}},
    )
    response = await api_client.get("/usage")

    assert response.status_code == 200
    item = response.json()["usage"][0]
    assert item["report_name"] == "Alt-Path Report"
    assert item["credits_used"] == 12.5
