"""Chat service: answer questions over a dataset and persist the conversation."""

from __future__ import annotations

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.chat_agent import ChatAgent
from app.agents.profiling_agent import ProfilingAgent
from app.models.chat import ChatMessage, ChatSession
from app.repositories.chat_repository import ChatMessageRepository, ChatSessionRepository
from app.schemas.chat import (
    ChatHistoryMessage,
    ChatHistoryResponse,
    ChatRequest,
    ChatResponse,
)
from app.services.base import BaseService, DatasetContextMixin


class ChatService(BaseService, DatasetContextMixin):
    """Coordinates the chat agent and persists chat history."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.sessions = ChatSessionRepository(db)
        self.messages = ChatMessageRepository(db)
        self.profiling_agent = ProfilingAgent()
        self.chat_agent = ChatAgent()

    def ask(self, dataset_id: int, user_id: int, payload: ChatRequest) -> ChatResponse:
        """Answer a question and persist both the question and the answer."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        session = self._resolve_session(payload.session_id, dataset_id, user_id, payload.question)

        ctx = self._build_context(dataset)
        self.profiling_agent.run(ctx)  # gives the planner semantic column types

        # Recent turns give the agent conversation memory for follow-ups
        # ("generate the graph", "now filter that to 2024").
        history = [
            {"role": m.role, "content": m.content, "sql": m.generated_sql or ""}
            for m in self.messages.list_for_session(session.id)
        ][-8:]
        answer = self.chat_agent.ask(ctx, payload.question, history=history)

        self.messages.create(session_id=session.id, role="user", content=payload.question, created_by=user_id)
        self.messages.create(
            session_id=session.id, role="assistant", content=answer.answer,
            generated_sql=answer.sql,
            result_preview={"columns": answer.columns, "rows": answer.rows[:20]},
            chart_spec=answer.chart_spec, created_by=user_id,
        )
        self.db.commit()

        return ChatResponse(
            answer=answer.answer, sql=answer.sql, columns=answer.columns,
            rows=answer.rows, row_count=answer.row_count,
            chart_spec=answer.chart_spec, session_id=session.id,
        )

    def get_history(self, dataset_id: int, user_id: int) -> ChatHistoryResponse:
        """Return the most recent chat session's messages for a dataset."""
        self._load_owned_dataset(dataset_id, user_id)
        session = self.sessions.latest_for_dataset(dataset_id, user_id)
        if session is None:
            return ChatHistoryResponse(session_id=None, messages=[])
        messages = []
        for m in self.messages.list_for_session(session.id):
            preview = m.result_preview or {}
            messages.append(ChatHistoryMessage(
                role=m.role, content=m.content, sql=m.generated_sql,
                columns=preview.get("columns", []), rows=preview.get("rows", []),
                chart_spec=m.chart_spec,
            ))
        return ChatHistoryResponse(session_id=session.id, messages=messages)

    def clear_history(self, dataset_id: int, user_id: int) -> None:
        """Delete all chat sessions and messages for a dataset owned by the user."""
        self._load_owned_dataset(dataset_id, user_id)
        session_ids = list(
            self.db.scalars(
                select(ChatSession.id).where(
                    ChatSession.dataset_id == dataset_id, ChatSession.user_id == user_id
                )
            ).all()
        )
        if session_ids:
            self.db.execute(sa_delete(ChatMessage).where(ChatMessage.session_id.in_(session_ids)))
        self.db.execute(
            sa_delete(ChatSession).where(
                ChatSession.dataset_id == dataset_id, ChatSession.user_id == user_id
            )
        )
        self.db.commit()

    def _resolve_session(self, session_id, dataset_id, user_id, question) -> ChatSession:
        if session_id:
            session = self.sessions.get(session_id)
            if session and session.user_id == user_id:
                return session
        title = (question[:40] + "...") if len(question) > 40 else question
        session = self.sessions.create(
            user_id=user_id, dataset_id=dataset_id, title=title, created_by=user_id
        )
        self.db.flush()
        return session
