"""Dataset, column and uploaded-file repositories."""

from __future__ import annotations

from sqlalchemy import select

from app.models.dataset import Dataset, DatasetColumn, UploadedFile
from app.repositories.base import BaseRepository


class UploadedFileRepository(BaseRepository[UploadedFile]):
    """Database operations for :class:`UploadedFile`."""

    model = UploadedFile


class DatasetRepository(BaseRepository[Dataset]):
    """Database operations for :class:`Dataset`."""

    model = Dataset

    def get_owned(self, dataset_id: int, user_id: int) -> Dataset | None:
        """Return a dataset only if it belongs to the given user."""
        entity = self.get(dataset_id)
        if entity is None or entity.user_id != user_id:
            return None
        return entity


class DatasetColumnRepository(BaseRepository[DatasetColumn]):
    """Database operations for :class:`DatasetColumn`."""

    model = DatasetColumn

    def list_for_dataset(self, dataset_id: int) -> list[DatasetColumn]:
        """Return all column profiles for a dataset ordered by position."""
        stmt = (
            select(DatasetColumn)
            .where(DatasetColumn.dataset_id == dataset_id, DatasetColumn.is_deleted.is_(False))
            .order_by(DatasetColumn.ordinal.asc())
        )
        return list(self.db.scalars(stmt).all())

    def delete_for_dataset(self, dataset_id: int) -> None:
        """Soft-delete existing column profiles before re-profiling."""
        for column in self.list_for_dataset(dataset_id):
            column.is_deleted = True
            self.db.add(column)
        self.db.flush()
