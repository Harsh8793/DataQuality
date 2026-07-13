"""Dataset edit repository."""

from __future__ import annotations

from sqlalchemy import select

from app.models.edit import DatasetEdit
from app.repositories.base import BaseRepository


class EditRepository(BaseRepository[DatasetEdit]):
    """Database operations for :class:`DatasetEdit`."""

    model = DatasetEdit

    def latest_for_dataset(self, dataset_id: int) -> DatasetEdit | None:
        """Return the most recent edit batch for a dataset."""
        stmt = (
            select(DatasetEdit)
            .where(DatasetEdit.dataset_id == dataset_id, DatasetEdit.is_deleted.is_(False))
            .order_by(DatasetEdit.id.desc())
        )
        return self.db.scalars(stmt).first()

    def list_for_dataset(self, dataset_id: int, limit: int = 20) -> list[DatasetEdit]:
        """Return recent edit batches for a dataset, newest first."""
        stmt = (
            select(DatasetEdit)
            .where(DatasetEdit.dataset_id == dataset_id, DatasetEdit.is_deleted.is_(False))
            .order_by(DatasetEdit.id.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())
