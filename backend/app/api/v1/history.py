"""History endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import CurrentUser
from app.schemas.common import ApiResponse, PageMeta, PaginatedResponse
from app.services.history_service import HistoryService

router = APIRouter(prefix="/history", tags=["History"])


@router.get("", response_model=ApiResponse[PaginatedResponse[dict]])
def get_history(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Return the user's activity timeline."""
    items, total = HistoryService(db).timeline(current_user.id, limit, offset)
    page = PaginatedResponse(
        items=items,
        meta=PageMeta(total=total, limit=limit, offset=offset, has_more=offset + limit < total),
    )
    return ApiResponse.ok(page)
