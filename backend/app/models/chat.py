"""Chat session and message models (chat-with-data history)."""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import AuditMixin, Base


class ChatSession(AuditMixin, Base):
    """A conversation thread scoped to a single dataset."""

    __tablename__ = "chat_history"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    dataset_id: Mapped[int] = mapped_column(Integer, ForeignKey("datasets.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="New chat")

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ChatMessage(AuditMixin, Base):
    """A single chat turn (user question or assistant answer)."""

    __tablename__ = "chat_messages"

    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("chat_history.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    generated_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_preview: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    chart_spec: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
