"""Quality report, quality issue and analysis history repositories."""

from __future__ import annotations

from sqlalchemy import select

from app.models.analysis import AnalysisHistory, QualityIssue, QualityReport
from app.repositories.base import BaseRepository


class QualityReportRepository(BaseRepository[QualityReport]):
    """Database operations for :class:`QualityReport`."""

    model = QualityReport

    def latest_for_dataset(self, dataset_id: int) -> QualityReport | None:
        """Return the most recent quality report for a dataset."""
        stmt = (
            select(QualityReport)
            .where(QualityReport.dataset_id == dataset_id, QualityReport.is_deleted.is_(False))
            .order_by(QualityReport.created_at.desc())
        )
        return self.db.scalars(stmt).first()


class QualityIssueRepository(BaseRepository[QualityIssue]):
    """Database operations for :class:`QualityIssue`."""

    model = QualityIssue

    def list_for_report(self, report_id: int) -> list[QualityIssue]:
        """Return all issues for a quality report."""
        stmt = (
            select(QualityIssue)
            .where(QualityIssue.report_id == report_id, QualityIssue.is_deleted.is_(False))
            .order_by(QualityIssue.severity.asc())
        )
        return list(self.db.scalars(stmt).all())


class AnalysisHistoryRepository(BaseRepository[AnalysisHistory]):
    """Database operations for :class:`AnalysisHistory`."""

    model = AnalysisHistory
