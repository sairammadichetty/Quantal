"""Pydantic models for responses returned by the upstream Orbital services.

We validate upstream payloads at the boundary rather than trusting them
blindly. If the upstream ever changes shape (a new required field, a rename,
a type change) the failure will surface here with a clear error rather than
as a confusing `KeyError` deep inside the credit calculation.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    """A single raw message as returned by `/messages/current-period`."""

    id: int
    # ISO-8601 string. Kept as `str` so we re-emit the exact format we received.
    timestamp: str
    # `text` is optional because report-only messages do not strictly need it
    # (the brief says "ignore the message text" when a report_id is present).
    text: Optional[str] = None
    report_id: Optional[int] = None

    model_config = ConfigDict(extra="ignore")


class Report(BaseModel):
    """A report's billing metadata as returned by `/reports/{id}`."""

    name: str
    # The brief describes this as a fixed number of credits. We accept either
    # int or float from the upstream and coerce to float for downstream use.
    credit_cost: float = Field(..., ge=0)

    model_config = ConfigDict(extra="ignore")
