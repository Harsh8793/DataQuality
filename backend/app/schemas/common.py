"""Shared response envelope and pagination schemas.

Every API returns the standard envelope::

    {success, message, data, errors, timestamp}

so the frontend can handle all responses uniformly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


def _now() -> datetime:
    """Timezone-aware UTC timestamp for response envelopes."""
    return datetime.now(timezone.utc)


class ErrorDetail(BaseModel):
    """A single structured error entry."""

    code: str
    message: str
    field: str | None = None


class ApiResponse(BaseModel, Generic[T]):
    """Standard success/response envelope used by every endpoint."""

    success: bool = True
    message: str = "OK"
    data: T | None = None
    errors: list[ErrorDetail] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=_now)

    @classmethod
    def ok(cls, data: T | None = None, message: str = "OK") -> "ApiResponse[T]":
        """Build a successful response envelope."""
        return cls(success=True, message=message, data=data)

    @classmethod
    def fail(cls, message: str, errors: list[ErrorDetail] | None = None) -> "ApiResponse[T]":
        """Build a failed response envelope."""
        return cls(success=False, message=message, data=None, errors=errors or [])


class PageMeta(BaseModel):
    """Pagination metadata."""

    total: int
    limit: int
    offset: int
    has_more: bool


class PaginatedResponse(BaseModel, Generic[T]):
    """A page of items plus pagination metadata."""

    items: list[T]
    meta: PageMeta
