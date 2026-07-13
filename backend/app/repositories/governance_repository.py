"""Governance repository."""

from __future__ import annotations

from sqlalchemy import select

from app.models.governance import GovernanceReport
from app.repositories.base import BaseRepository


class GovernanceRepository(BaseRepository[GovernanceReport]):
    """Database operations for :class:`GovernanceReport`."""

    model = GovernanceReport

    def latest_for_dataset(self, dataset_id: int) -> GovernanceReport | None:
        """Return the most recent governance report for a dataset."""
        stmt = (
            select(GovernanceReport)
            .where(GovernanceReport.dataset_id == dataset_id, GovernanceReport.is_deleted.is_(False))
            .order_by(GovernanceReport.created_at.desc())
        )
        return self.db.scalars(stmt).first()
