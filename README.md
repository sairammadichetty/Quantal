# Quantal — Orbital Copilot Usage API

Small FastAPI service that aggregates Orbital Copilot message and report data into a consumption-based credit breakdown for the current billing period.

Exposes a single endpoint, `GET /usage`, whose response matches the contract in the take-home brief.

---

## Quick start

### Option A — Python venv

Requires Python 3.10+ (tested with 3.11).

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the app
uvicorn app.main:app --reload --port 8000

# In another shell
curl -s http://localhost:8000/usage | jq .
curl -s http://localhost:8000/healthz
```

### Option B — Docker

```bash
docker compose up --build
curl -s http://localhost:8000/usage | jq .
```

### Tests

```bash
pytest
```

The test suite is fully offline: upstream calls are served by
`httpx.MockTransport` so there is no dependency on external availability.

### Lint / format / type-check

Dev tooling is pinned in `requirements-dev.txt`:

```bash
pip install -r requirements-dev.txt
```

Then the five quality gates (in the same order CI runs them):

```bash
ruff check .              # Lint
ruff format --check .     # Formatting (use `ruff format .` to apply)
mypy app                  # Strict static type checking for the app package
pytest -q                 # Tests
gitleaks detect --no-git  # Secret scan (also runs via pre-commit)
```

Install the pre-commit hook once per clone so the same checks run on
every commit:

```bash
pre-commit install
pre-commit run --all-files
```

CI (`.github/workflows/ci.yml`) runs the same gates on push/PR, plus a
parallel `docker-build` job that builds the production image and probes
`/healthz` so Dockerfile regressions get caught before deploy.

---

## Contract

```
GET /usage
```

```json
{
  "usage": [
    { "message_id": 1, "timestamp": "2024-04-29T02:08:29.375Z", "credits_used": 4.6 },
    { "message_id": 2, "timestamp": "2024-04-29T02:09:04.000Z", "report_name": "Short Lease Report", "credits_used": 79 }
  ]
}
```

- Field names (`message_id`, `timestamp`, `report_name`, `credits_used`)
  are frozen — multiple teams consume this, so the names are
  contract. `test_contract_field_names_and_presence` is the tripwire.
- `report_name` is **omitted** (not `null`) when there's no associated
  report. Enforced via `response_model_exclude_none=True` on the route.
- `credits_used` is rounded to 2dp.

---

## Project layout

```
app/
  main.py                  # Composition root: lifespan, routers, logging
  api/v1/endpoints.py      # /usage route — thin, delegates to the service
  core/
    config.py              # Pydantic settings (env-driven, .env-aware)
    credit_logic.py        # Pure text-based credit calculation
  services/
    orbital_client.py      # Async client for upstream endpoints
    usage_service.py       # Orchestrates messages + reports + credits
  schemas/
    usage.py               # Public response contract
    upstream.py            # Validated upstream payloads
tests/
  conftest.py              # MockTransport factories & ASGI fixtures
  test_credit_logic.py     # Unit tests, one per rule in the brief
  test_api.py              # End-to-end via ASGITransport + mocked upstream
```

Business logic (`core/`, `services/usage_service.py`) is kept separate
from FastAPI so it can be unit-tested and reused.

---

## Architecture

A small, layered architecture with dependency injection — loosely inspired by Hexagonal / Clean Architecture but kept deliberately lightweight for a service of this size.

```
┌──────────────────────────────────────────────────────────────┐
│  Transport        api/v1/endpoints.py     main.py            │
│  (FastAPI routes, error mapping, composition root)           │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│  Orchestration    services/usage_service.py                  │
│  (messages + reports + credit rules → UsageResponse)         │
└─────────────┬──────────────────────────────┬─────────────────┘
              │                              │
              ▼                              ▼
┌──────────────────────────┐     ┌───────────────────────────┐
│  Domain (pure)           │     │  Infrastructure adapter   │
│  core/credit_logic.py    │     │  services/orbital_client  │
│  (no I/O, no framework)  │     │  (async HTTP upstream)    │
└──────────────────────────┘     └───────────────────────────┘

                   validated via
┌──────────────────────────────────────────────────────────────┐
│  Schemas          schemas/usage.py    schemas/upstream.py    │
│  (public contract,     upstream payloads — anti-corruption)  │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  Cross-cutting    core/config.py (env-driven settings)       │
└──────────────────────────────────────────────────────────────┘
```

### Patterns in play

- **Layered architecture.** Transport → orchestration → domain / infrastructure. Each layer knows only about the one below.
- **Pure domain core.** `credit_logic.py` is a plain function operating on `Decimal` — no I/O, no FastAPI, trivial to unit-test.
- **Dependency injection via `Depends`.** Routes don't construct their own `OrbitalClient`; the app's lifespan owns a pooled `httpx.AsyncClient` and `Depends(get_orbital_client)` hands it in. Tests swap the underlying transport for an `httpx.MockTransport` with zero changes to the service or route.
- **Composition root.** `app/main.py` is the only place that wires logging, the HTTP client lifecycle, and routers together Nothing below it knows how it was assembled.
- **Ports & adapters (lightweight).** `OrbitalClient` is the single adapter in front of the upstream. Retry/caching/metrics would land here without touching the service layer.
- **Anti-corruption layer at boundaries.** Two separate schema modules:
  `schemas/upstream.py` validates what comes in from Orbital;
  `schemas/usage.py` defines what goes out. An upstream shape change fails fast with a clear Pydantic error instead of a `KeyError` mid credit-calculation.
- **12-factor config.** All tunables live in `.env` / env vars and are validated at boot by Pydantic settings.


### Request flow

```
HTTP GET /usage
   │
   ▼
endpoints.get_usage()              ← maps errors to HTTP status codes
   │
   ▼
build_usage_response(client)       ← orchestration
   │
   ├──► client.get_messages()      ← infra (HTTP)
   │
   ├──► asyncio.gather(            ← concurrent, deduplicated
   │      client.get_report(id)    ←   infra (HTTP)
   │      for id in unique_ids
   │    )
   │
   └──► calculate_text_credits()   ← pure domain (fallback path only)
```

---

## Configuration

All tunables live in `.env` — see `.env.example`. Upstream paths are in
config so a new billing period or a v2 reports route is a deploy change,
not a code change:

| Variable | Default | Notes |
|---|---|---|
| `ORBITAL_BASE_URL` | `https://owpublic.blob.core.windows.net/tech-task` | Upstream host + prefix |
| `ORBITAL_MESSAGES_PATH` | `/messages/current-period` | Override for a different period, e.g. `/messages/2025-Q1` |
| `ORBITAL_REPORT_PATH_TEMPLATE` | `/reports/{report_id}` | Must contain `{report_id}` — validated at boot |
| `ORBITAL_HTTP_TIMEOUT_SECONDS` | `10.0` | Per-request timeout |

`tests/test_api.py::test_messages_path_is_configurable` and
`test_report_template_is_configurable` prove both paths flow end-to-end.

---

## Notes on a few decisions

### Decimal-based credit calc
All the intermediate maths uses `decimal.Decimal`, not `float`. Adding a
pile of `0.05`, `0.1`, `0.2` values in binary float accumulates drift
(`0.1 + 0.2 == 0.30000000000000004`), which makes tests flaky and,
worse, can give customers cents that don't match the spec. The final
value is quantised to 2dp with `ROUND_HALF_UP` before hitting JSON.

### Word definition
The brief says *"any continual sequence of letters, plus ' and -"*. A
naïve `[a-zA-Z'-]+` also matches standalone junk like `-`, `'`, `--`
and would charge the short-word multiplier for them. The regex used
(`[A-Za-z'-]*[A-Za-z][A-Za-z'-]*`) requires at least one letter per
match, so punctuation-only tokens don't count as words.

### The 1-credit floor and palindromes
Two rules interact:

1. Unique-word bonus: subtract 2, *"minimum cost should still be 1 credit"*.
2. Palindrome: double the total *"after all other rules have been applied"*.

I floor at 1.0 **before** the palindrome doubling. Flooring only at the
very end gives `max(1, doubled-after-bonus)` and the palindrome rule
becomes a no-op for short inputs. With the order I chose, `"aba" -> 2.0`,
which matches intuition and lines up with the test suite. Called out in
a comment in `credit_logic.py`.

### Shared httpx client via FastAPI lifespan
The original version created a new `httpx.AsyncClient` per request,
which burns a TCP + TLS handshake every call. Now the app owns one
client in `app.state.http_client` for the lifespan, and a lightweight
`OrbitalClient` wrapper is injected per request via `Depends`. Free
connection pooling, no bookkeeping in handlers.

### Concurrent, deduplicated report lookups
Messages often share `report_id`s. I collect unique IDs (preserving
first-seen order via `dict.fromkeys`), fan out with `asyncio.gather`,
and put the results back in a dict for O(1) lookup per message.
`return_exceptions=True` means a single flaky report doesn't blow up
the whole `/usage` — we log it and fall back to text calc for that one
message.

### Error mapping
- Messages endpoint non-2xx → `502 Bad Gateway`.
- Network failure (timeout, connection reset) → `504 Gateway Timeout`.
- Report endpoint `404` → documented fallback to text calc.
- Report endpoint any other error → logged, fall back per-message.

### Pydantic validation at the upstream boundary
Upstream payloads go through `schemas/upstream.py` so a shape change
surfaces with a clear error rather than a `KeyError` mid-calculation.

### `report_name` omitted, not null
Enforced on the route with `response_model_exclude_none=True`. Note this
is a route-level setting, not `model_config` — Pydantic's default
`model_dump` keeps `None` values, which is a common gotcha.

---

## Things I left out

Given more time I'd add:

- **Retries / circuit breaker.** `tenacity`-style backoff on 5xx / network errors.
- **Caching reports.** They look immutable for a billing period; in-memory per-process, or Redis for a horizontal deploy.
- **Pagination** on `get_messages` — a real upstream probably paginates.
- **OpenTelemetry / Prometheus** on top of the logging that's already scaffolded.
- **Auth / rate limiting** — the brief implied an internal service so I skipped these.
- **Hypothesis property tests** for the credit engine (Unicode, extreme lengths).

---
### Here is the thoughtprocess on how did I look at the task and How I made decision to execute the take home task

### Design 1 — Implemented
## How I'd evolve this under real load

What's in the repo today is "Design 1" — a single process, one upstream, one `/usage` endpoint. That's deliberate: the brief is a focused take-home, and I didn't want to over-engineer. But a reviewer will reasonably ask *"what happens when this gets real traffic, or real data?"*, so here's how I'd think about the next two steps.

### Design 2 — if there is more traffic

The first things that break under load aren't usually the business logic; they're the boring operational bits. So:

- **Run it on Kubernetes**, as a plain `Deployment`. Readiness/liveness probes hit `/healthz` (already wired up), rolling updates for zero downtime.
- **Scale with an HPA** — start on CPU, but I'd want to move to request rate (QPS) via Prometheus adapter fairly quickly because this service spends most of its time waiting on I/O and CPU is a poor signal for that.
- **Cache reports in Redis**, not in-process. Reports look immutable for a given billing period, so they're a near-perfect cache candidate.
- **Keep the service stateless.**
- **Observability.** Ship structured logs to whatever the org uses (Datadog / ELK / Cloud Logging), and add Prometheus metrics for latency, error rate, upstream call counts.
- **Ingress + LB**  handling TLS and routing.

Note: Nothing here changes the application code meaningfully, the layering already supports it.

### Design 3 — if there is lot more data

The shape of the problem changes once the volume does. At some point `/usage` computing credits on the fly across tens of thousands of messages per request is the wrong model, regardless of how much we scale horizontally.
So I'd flip it:

- **Own the data.** Persist messages and reports in a database. Now Upstream becomes an ingest concern, not a request-path concern.
- **Precompute credits.** Do the expensive work once, asynchronously,and store the result. `/usage` then becomes a paginated read against an indexed table.
- **Drive ingestion off a queue** (SQS / Kafka, depending on what the org runs). New messages or report updates publish an event; workers consume, calculate, write.
- **Still cache hot reads** in Redis in front of the DB for dashboards and repeat queries, but with the DB as the source of truth it's a much simpler cache to reason about.
- **Take schema evolution seriously.** Versioned migrations

### Conclusion
**Design 1** is what I'd ship for this take-home,
**Design 2** is what I'd reach for when we started seeing a lot of customers traffic, and
**Design 3** is what I'd push for before the dataset outgrows "fits comfortably in a single HTTP call".
