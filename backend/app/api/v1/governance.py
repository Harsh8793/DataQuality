"""Governance and metadata endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import CurrentUser
from app.schemas.chat import GovernanceResponse
from app.schemas.common import ApiResponse
from app.services.governance_service import GovernanceService

router = APIRouter(prefix="/datasets", tags=["Governance"])


@router.get("/{dataset_id}/governance", response_model=ApiResponse[GovernanceResponse])
def get_governance(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Classify a dataset's sensitivity and recommend an ingestion tier."""
    return ApiResponse.ok(GovernanceService(db).classify(dataset_id, current_user.id))
