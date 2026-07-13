"""Authentication endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import CurrentUser
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.schemas.common import ApiResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=ApiResponse[TokenResponse])
def register(payload: RegisterRequest, db: Annotated[Session, Depends(get_db)]):
    """Register a new user and return an access token."""
    token = AuthService(db).register(payload)
    return ApiResponse.ok(token, message="Registration successful.")


@router.post("/login", response_model=ApiResponse[TokenResponse])
def login(payload: LoginRequest, db: Annotated[Session, Depends(get_db)]):
    """Authenticate a user and return an access token."""
    token = AuthService(db).login(payload)
    return ApiResponse.ok(token, message="Login successful.")


@router.get("/me", response_model=ApiResponse[UserResponse])
def me(current_user: CurrentUser):
    """Return the currently authenticated user."""
    user = UserResponse(
        id=current_user.id, name=current_user.name,
        email=current_user.email, role=current_user.role,
    )
    return ApiResponse.ok(user)
