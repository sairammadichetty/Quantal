"""Public contract for the /usage endpoint."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UsageItem(BaseModel):
    message_id: int
    timestamp: str
    # Omitted from JSON when None via response_model_exclude_none=True on
    # the route. Declaration order here also drives serialisation order.
    report_name: str | None = Field(default=None)
    credits_used: float

    model_config = ConfigDict(extra="ignore")


class UsageResponse(BaseModel):
    usage: list[UsageItem]
