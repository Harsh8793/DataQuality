"""Chat session and message repositories."""

from __future__ import annotations

from sqlalchemy import select

from app.models.chat import ChatMessage, ChatSession
from app.repositories.base import BaseRepository


class ChatSessionRepository(BaseRepository[ChatSession]):
    """Database operations for :class:`ChatSession`."""

    model = ChatSession

    def latest_for_dataset(self, dataset_id: int, user_id: int) -> ChatSession | None:
        """Return the most recent chat session for a dataset owned by the user."""
        stmt = (
            select(ChatSession)
            .where(
                ChatSession.dataset_id == dataset_id,
                ChatSession.user_id == user_id,
                ChatSession.is_deleted.is_(False),
            )
            .order_by(ChatSession.created_at.desc())
        )
        return self.db.scalars(stmt).first()


class ChatMessageRepository(BaseRepository[ChatMessage]):
    """Database operations for :class:`ChatMessage`."""

    model = ChatMessage

    def list_for_session(self, session_id: int) -> list[ChatMessage]:
        """Return messages for a session in chronological order."""
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id, ChatMessage.is_deleted.is_(False))
            .order_by(ChatMessage.created_at.asc())
        )
        return list(self.db.scalars(stmt).all())
