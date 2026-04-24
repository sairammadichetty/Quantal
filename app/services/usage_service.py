"""Builds the /usage response from messages + reports + credit rules."""

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

    A value of None in the returned dict means either a documented 404 or
    an unexpected error — both fall back to text-based calc, so the caller
    doesn't need to tell them apart.
    """
    if not report_ids:
        return {}

    # return_exceptions=True so one flaky report doesn't nuke /usage for
    # every other message in the period.
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
            report_map[rid] = result
    return report_map


def _build_usage_item(message: Message, report: Report | None) -> UsageItem:
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
    )


async def build_usage_response(client: OrbitalClient) -> UsageResponse:
    """Compose the full `/usage` response.

    1. Fetch messages.
    2. Batch-fetch unique reports concurrently.
    3. For each message, attach its report metadata (if any) and compute credits.
    """
    messages = await client.get_messages()

    # Deduplicate before fanning out so upstream load is O(unique reports),
    # not O(messages). dict.fromkeys preserves first-seen order.
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
