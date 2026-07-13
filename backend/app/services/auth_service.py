"""Authentication service: registration, login and token issuance."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.exceptions.base import ConflictException, UnauthorizedException
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.base import BaseService


class AuthService(BaseService):
    """Business logic for local authentication."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.users = UserRepository(db)

    def register(self, payload: RegisterRequest) -> TokenResponse:
        """Register a new user and return an access token."""
        if self.users.get_by_email(payload.email):
            raise ConflictException("An account with this email already exists.")
        user = self.users.create(
            name=payload.name,
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            role="analyst",
        )
        self.db.commit()
        self.logger.info("Registered user %s", user.email)
        return self._issue_token(user)

    def login(self, payload: LoginRequest) -> TokenResponse:
        """Authenticate a user and return an access token."""
        user = self.users.get_by_email(payload.email)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise UnauthorizedException("Invalid email or password.")
        return self._issue_token(user)

    def get_user(self, user_id: int) -> User:
        """Return a user by id or raise if not found."""
        user = self.users.get(user_id)
        if user is None:
            raise UnauthorizedException("User no longer exists.")
        return user

    def _issue_token(self, user: User) -> TokenResponse:
        # JWT subject must be a string; user ids are integers.
        token = create_access_token(str(user.id), extra={"role": user.role})
        return TokenResponse(
            access_token=token,
            user=UserResponse(id=user.id, name=user.name, email=user.email, role=user.role),
        )
