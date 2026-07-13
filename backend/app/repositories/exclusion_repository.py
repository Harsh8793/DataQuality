"""Issue-exclusion repository."""

from __future__ import annotations

from sqlalchemy import select

from app.models.exclusion import IssueExclusion
from app.repositories.base import BaseRepository


class ExclusionRepository(BaseRepository[IssueExclusion]):
    """Database operations for :class:`IssueExclusion`."""

    model = IssueExclusion

    def list_for_dataset(self, dataset_id: int) -> list[IssueExclusion]:
        stmt = (
            select(IssueExclusion)
            .where(IssueExclusion.dataset_id == dataset_id, IssueExclusion.is_deleted.is_(False))
            .order_by(IssueExclusion.id.desc())
        )
        return list(self.db.scalars(stmt).all())

    def find(self, dataset_id: int, check_key: str, column_name: str | None) -> IssueExclusion | None:
        stmt = select(IssueExclusion).where(
            IssueExclusion.dataset_id == dataset_id,
            IssueExclusion.check_key == check_key,
            IssueExclusion.column_name.is_(column_name) if column_name is None
            else IssueExclusion.column_name == column_name,
            IssueExclusion.is_deleted.is_(False),
        )
        return self.db.scalars(stmt).first()
