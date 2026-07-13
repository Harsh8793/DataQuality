"""Generated report and dashboard repositories."""

from __future__ import annotations

from sqlalchemy import select

from app.models.report import DashboardHistory, GeneratedReport
from app.repositories.base import BaseRepository


class ReportRepository(BaseRepository[GeneratedReport]):
    """Database operations for :class:`GeneratedReport`."""

    model = GeneratedReport


class DashboardRepository(BaseRepository[DashboardHistory]):
    """Database operations for :class:`DashboardHistory`."""

    model = DashboardHistory

    def latest_for_dataset(self, dataset_id: int) -> DashboardHistory | None:
        """Return the most recent cached dashboard spec for a dataset."""
        stmt = (
            select(DashboardHistory)
            .where(DashboardHistory.dataset_id == dataset_id, DashboardHistory.is_deleted.is_(False))
            .order_by(DashboardHistory.created_at.desc())
        )
        return self.db.scalars(stmt).first()
