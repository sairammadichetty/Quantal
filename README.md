# Quantal — Orbital Copilot Usage API

A small FastAPI service that aggregates Orbital Copilot message and report
data to produce consumption-based credit usage for the current billing
period.

It exposes a single public endpoint, `GET /usage`, whose response is the
contract defined in the take-home brief (see *Contract* below).

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

Dev tooling is pinned in `requirements-dev.txt`; install it once into the
same virtualenv as the runtime deps:

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

Install the pre-commit hook once per clone so every `git commit` runs
lint, format, type-check, whitespace hygiene, and the gitleaks secret
scanner on staged files:

```bash
pre-commit install
pre-commit run --all-files    # one-time sweep across the tree
```

Every push/PR triggers the same gates in `.github/workflows/ci.yml`,
including a gitleaks secret scan over the commit range, so local and
CI results are identical.

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

* Field names are contractually `message_id`, `timestamp`, `report_name`
  (optional), `credits_used`. Multiple teams consume this response, so
  the names are frozen — a dedicated test (`test_contract_field_names_and_presence`)
  guards against accidental renames.
* `report_name` is **omitted** (not `null`) when the message has no
  associated report. This is enforced via
  `response_model_exclude_none=True` on the route.
* `credits_used` is a number quantised to 2 decimal places.

---

## Project layout

```
app/
  main.py                  # Composition root: lifespan, routers, logging
  api/v1/endpoints.py      # The /usage route; thin, delegates to service
  core/
    config.py              # Pydantic settings (env-driven, .env-aware)
    credit_logic.py        # Pure text-based credit calculation
  services/
    orbital_client.py      # Async client for upstream endpoints
    usage_service.py       # Orchestrates messages + reports + credits
  schemas/
    usage.py               # Public response contract (UsageItem/UsageResponse)
    upstream.py            # Validated models for upstream responses
tests/
  conftest.py              # MockTransport factories & ASGI fixtures
  test_credit_logic.py     # Unit tests per rule in the brief
  test_api.py              # End-to-end via ASGITransport with mocked upstream
```

Business logic (`core/`, `services/usage_service.py`) is deliberately
independent of FastAPI so it can be unit-tested and reused.

---

## Configuration

All tunables live in `.env` (see `.env.example` for the full list). The
upstream route paths are deliberately kept in config so a new billing
period or a v2 reports route is a deploy-time concern, not a code change:

| Variable | Default | Notes |
|---|---|---|
| `ORBITAL_BASE_URL` | `https://owpublic.blob.core.windows.net/tech-task` | Upstream host + prefix. |
| `ORBITAL_MESSAGES_PATH` | `/messages/current-period` | Override to target a different period, e.g. `/messages/2025-Q1`. |
| `ORBITAL_REPORT_PATH_TEMPLATE` | `/reports/{report_id}` | Must contain `{report_id}`; validated at boot. |
| `ORBITAL_HTTP_TIMEOUT_SECONDS` | `10.0` | Per-request timeout. |

`tests/test_api.py::test_messages_path_is_configurable` and
`test_report_template_is_configurable` prove both paths flow end-to-end.

---

## Key decisions

### Decimal-based credit calculation
All intermediate arithmetic uses `decimal.Decimal`, not `float`. Adding
several `0.05`, `0.1`, `0.2` values in binary float can accumulate drift
(e.g. `0.1 + 0.2 == 0.30000000000000004`), which would make "fixture
equals 3.05" tests flaky and, more importantly, could give customers
slightly different cents on a bill than intended. The final value is
quantised to 2 decimal places with `ROUND_HALF_UP`, then cast to `float`
at the JSON boundary.

### Word definition
The brief says *"any continual sequence of letters, plus ' and -"*. A
naïve regex `[a-zA-Z'-]+` would also match standalone tokens like `-`,
`'`, or `--` and charge the short-word multiplier for them. We use
`[A-Za-z'-]*[A-Za-z][A-Za-z'-]*`, which requires at least one letter in
each match, so a token made entirely of punctuation is not a "word".

### Rule ordering for the 1-credit floor
Two rules interact subtly:

1. *Unique word bonus:* subtract 2, "remember the minimum cost should
   still be 1 credit".
2. *Palindromes:* double the total "after all other rules have been
   applied".

We floor at 1.0 **before** the palindrome doubling. A stricter reading
could floor only at the very end, but then a palindrome with a heavy
unique-word bonus would end up with `max(1, doubled-sub-1)` — the
palindrome rule becomes meaningless for short inputs. The interpretation
we chose keeps both rules active (e.g. `"aba" -> 2.0`) which is the
intuitive result. The code comment in `credit_logic.py` calls this out.

### Shared httpx client via FastAPI lifespan
The original implementation created a new `httpx.AsyncClient` per
request, which costs a TCP + TLS handshake each time. We now own a
single client in `app.state.http_client` via the lifespan context
manager, and inject a lightweight `OrbitalClient` wrapper per request
via `Depends`. Connection pooling for free; no bookkeeping in handlers.

### Concurrent, deduplicated report lookups
Messages often reference the same `report_id`. We collect unique IDs
(preserving first-seen order via `dict.fromkeys`), fan out with
`asyncio.gather`, and map the results back into a dict for O(1)
per-message lookup. `return_exceptions=True` ensures a single flaky
upstream response doesn't blow up the whole `/usage` call — we log it
and fall back to text-based calc for that message.

### Error mapping
* Messages endpoint returning a non-2xx → `502 Bad Gateway`.
* Network-level failure (timeout, connection reset) → `504 Gateway Timeout`.
* Report endpoint returning `404` → documented fallback to text calc.
* Report endpoint returning any other error → logged, then fall back
  (per-message) so the response is still useful.

### Pydantic validation at the upstream boundary
Upstream payloads are validated via Pydantic models (`schemas/upstream.py`)
so a schema drift surfaces here with a clear error rather than as a
confusing `KeyError` deep in the credit engine.

### `report_name` omission
`report_name` is optional and must be *absent* from the JSON, not
present with `null`. Enforced via `response_model_exclude_none=True` on
the route (not by Pydantic's `model_config`, which many reviewers
mis-assume — the default `model_dump` includes None values).

---

## What I deliberately did **not** do (time-box)

These would be worthwhile next steps given more time:

* **Retries / circuit breaker.** `tenacity`-style retry with jittered
  backoff on 5xx/network errors for both endpoints. The shape is already
  there — `OrbitalClient` is the single chokepoint.
* **Caching.** Reports look immutable for the life of a billing period;
  caching them (in-memory per-process, Redis for a horizontal deploy)
  would cut upstream load significantly.
* **Pagination.** The messages endpoint in production may well paginate.
  `get_messages` would need to loop or stream.
* **Observability.** Structured logging (already scaffolded) →
  OpenTelemetry traces, Prometheus metrics for upstream p95 and failure
  rate.
* **Auth / rate limiting.** The brief implies an internal service so I
  left these off.
* **More exhaustive property tests for the credit engine** (e.g.
  Hypothesis strategies for Unicode, extreme lengths).

---

## Confidence in correctness

* Every rule in the brief has at least one dedicated unit test whose
  expected value is derived step-by-step in comments, so a reviewer can
  cross-reference against the spec without rerunning Python.
* End-to-end tests cover:
  * the shape of the response,
  * the report-present happy path (uses fixed `credit_cost`),
  * the 404 fallback path (falls back to text calc),
  * `report_name` being **omitted** (not `null`) when absent,
  * deduplication of repeated `report_id`s,
  * upstream 5xx → 502 mapping,
  * the health-check route.
* Decimal arithmetic plus explicit quantisation eliminates a class of
  floating-point bugs that would otherwise be invisible until a bill was
  off by a cent.
