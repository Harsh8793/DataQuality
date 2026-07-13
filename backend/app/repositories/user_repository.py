"""User repository."""

from __future__ import annotations

from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Database operations for :class:`User`."""

    model = User

    def get_by_email(self, email: str) -> User | None:
        """Return an active user by email address."""
        stmt = select(User).where(User.email == email.lower(), User.is_deleted.is_(False))
        return self.db.scalars(stmt).first()
