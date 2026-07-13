"""Authentication dependency: resolve the current user from a JWT."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database.session import get_db
from app.exceptions.base import UnauthorizedException
from app.models.user import User
from app.repositories.user_repository import UserRepository

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Resolve and return the authenticated user, or raise 401."""
    if credentials is None or not credentials.credentials:
        raise UnauthorizedException("Authentication required.")
    payload = decode_access_token(credentials.credentials)
    subject = payload.get("sub")
    if not subject:
        raise UnauthorizedException("Invalid authentication token.")
    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise UnauthorizedException("Invalid authentication token.")
    user = UserRepository(db).get(user_id)
    if user is None:
        raise UnauthorizedException("User no longer exists.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
