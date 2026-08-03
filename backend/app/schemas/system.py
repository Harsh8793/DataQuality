"""Schemas for system-level status endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.constants.enums import LlmStatus


class LlmStatusResponse(BaseModel):
    """Live health of the AI layer, shown on the dashboard KPI tile."""

    status: LlmStatus
    label: str
    model: str
    detail: str
    healthy: bool
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
