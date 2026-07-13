"""AI playground endpoints: explain, data story, comparison, starter questions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import CurrentUser
from app.schemas.ai import (
    CompareRequest,
    CompareResponse,
    ExplainRequest,
    ExplainResponse,
    StoryResponse,
    SuggestionsResponse,
)
from app.schemas.common import ApiResponse
from app.services.ai_service import AiService

router = APIRouter(prefix="/datasets", tags=["AI"])


@router.post("/{dataset_id}/explain", response_model=ApiResponse[ExplainResponse])
def explain_widget(
    dataset_id: int,
    payload: ExplainRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Explain a dashboard KPI or chart in plain business language."""
    return ApiResponse.ok(AiService(db).explain_widget(dataset_id, current_user.id, payload))


@router.get("/{dataset_id}/story", response_model=ApiResponse[StoryResponse])
def get_story(
    dataset_id: int,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    refresh: bool = False,
):
    """Return the AI executive summary for a dataset (cached after first call)."""
    return ApiResponse.ok(AiService(db).get_story(dataset_id, current_user.id, refresh))


@router.post("/compare", response_model=ApiResponse[CompareResponse])
def compare_datasets(
    payload: CompareRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Diff two datasets (schema + distribution shifts) with an AI narrative."""
    return ApiResponse.ok(AiService(db).compare(payload.left_id, payload.right_id, current_user.id))


@router.get("/{dataset_id}/chat/suggestions", response_model=ApiResponse[SuggestionsResponse])
def chat_suggestions(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Return data-aware starter questions for the chat panel."""
    return ApiResponse.ok(AiService(db).chat_suggestions(dataset_id, current_user.id))
