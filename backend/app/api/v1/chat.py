"""Chat-with-data endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import CurrentUser
from app.schemas.chat import ChatHistoryResponse, ChatRequest, ChatResponse
from app.schemas.common import ApiResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/datasets", tags=["Chat"])


@router.post("/{dataset_id}/chat", response_model=ApiResponse[ChatResponse])
def chat(
    dataset_id: int,
    payload: ChatRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Answer a natural-language question about the dataset."""
    answer = ChatService(db).ask(dataset_id, current_user.id, payload)
    return ApiResponse.ok(answer)


@router.get("/{dataset_id}/chat/history", response_model=ApiResponse[ChatHistoryResponse])
def chat_history(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Return the most recent chat session's messages for a dataset."""
    return ApiResponse.ok(ChatService(db).get_history(dataset_id, current_user.id))


@router.delete("/{dataset_id}/chat/history", response_model=ApiResponse[None])
def clear_chat_history(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Delete all chat history for a dataset."""
    ChatService(db).clear_history(dataset_id, current_user.id)
    return ApiResponse.ok(message="Chat history cleared.")
