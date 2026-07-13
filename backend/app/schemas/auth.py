"""Authentication request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Payload to register a new user."""

    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    """Payload to authenticate an existing user."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Public user representation."""

    id: int
    name: str
    email: str
    role: str


class TokenResponse(BaseModel):
    """Access token plus the authenticated user."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse
