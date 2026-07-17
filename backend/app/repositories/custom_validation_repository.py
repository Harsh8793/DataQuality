"""Custom validation repository."""

from __future__ import annotations

from sqlalchemy import select

from app.models.custom_validation import CustomValidation
from app.repositories.base import BaseRepository


class CustomValidationRepository(BaseRepository[CustomValidation]):
    """Database operations for :class:`CustomValidation`."""

    model = CustomValidation

    def list_for_dataset(self, dataset_id: int, active_only: bool = False) -> list[CustomValidation]:
        stmt = select(CustomValidation).where(
            CustomValidation.dataset_id == dataset_id, CustomValidation.is_deleted.is_(False)
        )
        if active_only:
            stmt = stmt.where(CustomValidation.is_active.is_(True))
        return list(self.db.scalars(stmt.order_by(CustomValidation.id.desc())).all())
