"""History service: retrieve analysis, chat and report history."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.analysis_repository import AnalysisHistoryRepository
from app.repositories.report_repository import ReportRepository
from app.services.base import BaseService


class HistoryService(BaseService):
    """Aggregates a user's activity history for the History view."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.analysis = AnalysisHistoryRepository(db)
        self.reports = ReportRepository(db)

    def timeline(self, user_id: str, limit: int, offset: int) -> tuple[list[dict], int]:
        """Return a paginated activity timeline and total count."""
        items = self.analysis.list(user_id=user_id, limit=limit, offset=offset)
        total = self.analysis.count(user_id=user_id)
        timeline = [
            {
                "id": item.id, "action": item.action, "summary": item.summary,
                "dataset_id": item.dataset_id, "payload": item.payload,
                "created_at": item.created_at,
            }
            for item in items
        ]
        return timeline, total
