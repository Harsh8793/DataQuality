"""Aggregate all v1 routers under a single API router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    ai,
    analysis,
    auth,
    chat,
    dashboard,
    edits,
    governance,
    history,
    reports,
    upload,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(ai.router)
api_router.include_router(edits.router)
api_router.include_router(upload.router)
api_router.include_router(analysis.router)
api_router.include_router(dashboard.router)
api_router.include_router(chat.router)
api_router.include_router(governance.router)
api_router.include_router(reports.router)
api_router.include_router(history.router)
