"""Cleaning report repository."""

from __future__ import annotations

from sqlalchemy import select

from app.models.cleaning import CleaningReport
from app.repositories.base import BaseRepository


class CleaningRepository(BaseRepository[CleaningReport]):
    """Database operations for :class:`CleaningReport`."""

    model = CleaningReport

    def latest_for_dataset(self, dataset_id: int) -> CleaningReport | None:
        """Return the most recent cleaning report for a dataset."""
        stmt = (
            select(CleaningReport)
            .where(CleaningReport.dataset_id == dataset_id, CleaningReport.is_deleted.is_(False))
            .order_by(CleaningReport.created_at.desc())
        )
        return self.db.scalars(stmt).first()
