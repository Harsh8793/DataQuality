"""Fix batch / issue fix repositories."""

from __future__ import annotations

from sqlalchemy import select

from app.models.fixes import FixBatch, IssueFix
from app.repositories.base import BaseRepository


class FixBatchRepository(BaseRepository[FixBatch]):
    """Database operations for :class:`FixBatch`."""

    model = FixBatch

    def latest_for_dataset(self, dataset_id: int) -> FixBatch | None:
        stmt = (
            select(FixBatch)
            .where(FixBatch.dataset_id == dataset_id, FixBatch.is_deleted.is_(False))
            .order_by(FixBatch.id.desc())
        )
        return self.db.scalars(stmt).first()

    def earliest_for_dataset(self, dataset_id: int) -> FixBatch | None:
        """The first batch, whose snapshot is the pre-fix state of the dataset.

        That snapshot is the baseline every rebuild replays from, so undoing a
        single fix out of the middle of the stack stays exact.
        """
        stmt = (
            select(FixBatch)
            .where(FixBatch.dataset_id == dataset_id, FixBatch.is_deleted.is_(False))
            .order_by(FixBatch.id.asc())
        )
        return self.db.scalars(stmt).first()

    def list_for_dataset(self, dataset_id: int) -> list[FixBatch]:
        """Every live batch, oldest first."""
        stmt = (
            select(FixBatch)
            .where(FixBatch.dataset_id == dataset_id, FixBatch.is_deleted.is_(False))
            .order_by(FixBatch.id.asc())
        )
        return list(self.db.scalars(stmt).all())


class IssueFixRepository(BaseRepository[IssueFix]):
    """Database operations for :class:`IssueFix`."""

    model = IssueFix

    def list_for_dataset(self, dataset_id: int, limit: int = 100) -> list[IssueFix]:
        stmt = (
            select(IssueFix)
            .where(IssueFix.dataset_id == dataset_id, IssueFix.is_deleted.is_(False))
            .order_by(IssueFix.id.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def list_for_dataset_chronological(self, dataset_id: int) -> list[IssueFix]:
        """Every live fix, oldest first — the order a rebuild must replay them in."""
        stmt = (
            select(IssueFix)
            .where(IssueFix.dataset_id == dataset_id, IssueFix.is_deleted.is_(False))
            .order_by(IssueFix.id.asc())
        )
        return list(self.db.scalars(stmt).all())

    def list_for_batch(self, batch_id: int) -> list[IssueFix]:
        stmt = (
            select(IssueFix)
            .where(IssueFix.batch_id == batch_id, IssueFix.is_deleted.is_(False))
            .order_by(IssueFix.id.asc())
        )
        return list(self.db.scalars(stmt).all())
