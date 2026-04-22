"""Response contract for the `/usage` endpoint.

The shape here is dictated by the task brief and is consumed by multiple
teams, so we intentionally keep the model strict and minimal. `report_name`
is `Optional[str]` on the model but is emitted to JSON only when non-null —
see `response_model_exclude_none=True` on the route.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class UsageItem(BaseModel):
    """A single row in the `usage` array.

    Field names here are part of a published contract agreed across
    multiple consuming teams — do not rename without a coordinated change.
    """

    message_id: int
    # Kept as `str` to preserve the exact ISO-8601 formatting the upstream
    # provides. Parsing to `datetime` would round-trip fine, but emitting
    # the same string the upstream returned avoids any microsecond/zone
    # drift that could surprise downstream consumers.
    timestamp: str

    # Optional by design: omitted from JSON when None via the endpoint's
    # `response_model_exclude_none=True`. We set a default so callers never
    # need to construct it explicitly. The contract defines this field as
    # appearing *before* `credits_used` when present; Pydantic honours the
    # declaration order below when serialising.
    report_name: Optional[str] = Field(default=None)

    # `float` is acceptable given the 2dp quantisation we apply in the
    # credit engine. For stricter money handling we could swap this for
    # `Decimal` with a `condecimal` constraint.
    credits_used: float

    model_config = ConfigDict(extra="ignore")


class UsageResponse(BaseModel):
    """Top-level response body: `{ "usage": [ ... ] }`."""

    usage: List[UsageItem]
