"""Pydantic models for upstream Orbital responses.

Validated at the boundary so a shape change surfaces here instead of as
a KeyError deep in the credit engine.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    id: int
    # Kept as a string so we re-emit exactly what the upstream gave us
    # (no timezone/microsecond round-trip surprises).
    timestamp: str
    text: str | None = None
    report_id: int | None = None

    model_config = ConfigDict(extra="ignore")


class Report(BaseModel):
    name: str
    credit_cost: float = Field(..., ge=0)

    model_config = ConfigDict(extra="ignore")
