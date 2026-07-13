"""Generic base repository implementing common CRUD with soft-delete."""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Reusable CRUD operations for a single ORM model.

    All reads exclude soft-deleted rows by default; deletes are soft.
    """

    model: type[ModelT]

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- create ------------------------------------------------------- #
    def create(self, **fields) -> ModelT:
        """Insert and return a new entity."""
        entity = self.model(**fields)
        self.db.add(entity)
        self.db.flush()
        self.db.refresh(entity)
        return entity

    def add(self, entity: ModelT) -> ModelT:
        """Persist an already-constructed entity instance."""
        self.db.add(entity)
        self.db.flush()
        self.db.refresh(entity)
        return entity

    # ---- read --------------------------------------------------------- #
    def get(self, entity_id: int) -> ModelT | None:
        """Return an entity by id, or ``None`` if missing/deleted."""
        entity = self.db.get(self.model, entity_id)
        if entity is None or getattr(entity, "is_deleted", False):
            return None
        return entity

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        order_desc: bool = True,
        **filters,
    ) -> list[ModelT]:
        """Return a filtered, paginated list of non-deleted entities."""
        stmt = select(self.model).where(self.model.is_deleted.is_(False))
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        order_col = self.model.created_at.desc() if order_desc else self.model.created_at.asc()
        stmt = stmt.order_by(order_col).limit(limit).offset(offset)
        return list(self.db.scalars(stmt).all())

    def count(self, **filters) -> int:
        """Count non-deleted entities matching the given filters."""
        stmt = select(func.count()).select_from(self.model).where(self.model.is_deleted.is_(False))
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        return int(self.db.scalar(stmt) or 0)

    # ---- update / delete --------------------------------------------- #
    def update(self, entity: ModelT, **fields) -> ModelT:
        """Apply field updates to an entity and flush."""
        for key, value in fields.items():
            setattr(entity, key, value)
        self.db.add(entity)
        self.db.flush()
        self.db.refresh(entity)
        return entity

    def soft_delete(self, entity: ModelT) -> None:
        """Mark an entity as deleted without removing the row."""
        entity.is_deleted = True
        self.db.add(entity)
        self.db.flush()
