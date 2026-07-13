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

    def list_for_batch(self, batch_id: int) -> list[IssueFix]:
        stmt = (
            select(IssueFix)
            .where(IssueFix.batch_id == batch_id, IssueFix.is_deleted.is_(False))
            .order_by(IssueFix.id.asc())
        )
        return list(self.db.scalars(stmt).all())
