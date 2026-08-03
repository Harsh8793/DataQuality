"""System status endpoints (runtime health surfaced in the UI)."""

from __future__ import annotations

from fastapi import APIRouter

from app.dependencies.auth import CurrentUser
from app.schemas.common import ApiResponse
from app.schemas.system import LlmStatusResponse
from app.services.system_service import SystemService

router = APIRouter(prefix="/system", tags=["System"])


@router.get("/llm", response_model=ApiResponse[LlmStatusResponse])
def llm_status(current_user: CurrentUser):
    """Report whether the AI layer is live, degraded, or switched off."""
    return ApiResponse.ok(SystemService().llm_status())
