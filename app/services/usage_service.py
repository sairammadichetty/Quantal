"""Usage computation orchestrator.

This is the single place that combines raw messages with report metadata
and the text-based credit rules to produce the `/usage` response body.

Design notes:
- The logic is kept separate from FastAPI so it can be unit-tested without
  spinning up an ASGI app: pass in a mocked `OrbitalClient` and assert on
  the returned `UsageResponse` directly.
- Report lookups are batched via `asyncio.gather`. We deduplicate report
  IDs first because multiple messages in the same period commonly reference
  the same report; this keeps upstream load O(unique reports) instead of
  O(messages).
- A single report failing (404 OR any other error) degrades gracefully to
  the text-based calculation for that individual message, rather than
  failing the whole `/usage` request. 404 is the documented fallback path;
  other errors are logged and treated the same way defensively.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.credit_logic import calculate_text_credits
from app.schemas.upstream import Message, Report
from app.schemas.usage import UsageItem, UsageResponse
from app.services.orbital_client import OrbitalClient

logger = logging.getLogger(__name__)


async def _fetch_reports(client: OrbitalClient, report_ids: list[int]) -> dict[int, Report | None]:
    """Fetch all unique report IDs concurrently.

    Returns a dict keyed by report_id. A value of `None` means either a
    documented 404 or an unexpected error — both lead to the same fallback
    behaviour (text-based calculation) so the caller doesn't need to
    distinguish them.
    """
    if not report_ids:
        return {}

    # `return_exceptions=True` is crucial: without it, a single failing
    # report fetch would abort the entire `gather`, losing the other
    # already-completed results and failing the `/usage` call for unrelated
    # messages. We convert exceptions to `None` and carry on.
    results = await asyncio.gather(
        *(client.get_report(rid) for rid in report_ids),
        return_exceptions=True,
    )

    report_map: dict[int, Report | None] = {}
    for rid, result in zip(report_ids, results, strict=False):
        if isinstance(result, BaseException):
            logger.warning(
                "Report lookup failed for id=%s, falling back to text calc: %r",
                rid,
                result,
            )
            report_map[rid] = None
        else:
            # `result` is narrowed to `Report | None` here — the `None` arm
            # represents a documented 404 fallback from the upstream.
            report_map[rid] = result
    return report_map


def _build_usage_item(message: Message, report: Report | None) -> UsageItem:
    """Turn one raw message (+ optional report) into a `UsageItem`.

    If a report is attached, we use its fixed `credit_cost` and `name`.
    Otherwise — including the 404-fallback case — we compute credits from
    the message text.
    """
    if report is not None:
        return UsageItem(
            message_id=message.id,
            timestamp=message.timestamp,
            report_name=report.name,
            credits_used=report.credit_cost,
        )

    return UsageItem(
        message_id=message.id,
        timestamp=message.timestamp,
        credits_used=calculate_text_credits(message.text or ""),
        # report_name left as None and stripped from JSON by
        # `response_model_exclude_none=True` on the route.
    )


async def build_usage_response(client: OrbitalClient) -> UsageResponse:
    """Compose the full `/usage` response.

    1. Fetch messages.
    2. Batch-fetch unique reports concurrently.
    3. For each message, attach its report metadata (if any) and compute credits.
    """
    messages = await client.get_messages()

    # Convert to a list (not a set) so gather/zip pairing is deterministic.
    # Using `dict.fromkeys` preserves first-seen order for readability of logs.
    unique_report_ids: list[int] = list(
        dict.fromkeys(m.report_id for m in messages if m.report_id is not None)
    )
    report_map = await _fetch_reports(client, unique_report_ids)

    items = [
        _build_usage_item(
            message,
            report_map.get(message.report_id) if message.report_id is not None else None,
        )
        for message in messages
    ]
    return UsageResponse(usage=items)
