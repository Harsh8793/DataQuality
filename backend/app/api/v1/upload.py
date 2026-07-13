"""Dataset upload and retrieval endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import CurrentUser
from app.schemas.common import ApiResponse, PageMeta, PaginatedResponse
from app.schemas.dataset import ApprovalRequest, DatasetPreview, DatasetSummary
from app.services.dataset_service import DatasetService

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.post("", response_model=ApiResponse[DatasetSummary])
async def upload_dataset(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
):
    """Upload a CSV/Excel/JSON file and register it as a dataset."""
    content = await file.read()
    summary = DatasetService(db).upload(current_user.id, file.filename or "upload", content)
    return ApiResponse.ok(summary, message="Dataset uploaded.")


@router.get("", response_model=ApiResponse[PaginatedResponse[DatasetSummary]])
def list_datasets(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List the current user's datasets (paginated)."""
    items, total = DatasetService(db).list(current_user.id, limit, offset)
    page = PaginatedResponse(
        items=items,
        meta=PageMeta(total=total, limit=limit, offset=offset, has_more=offset + limit < total),
    )
    return ApiResponse.ok(page)


@router.get("/{dataset_id}", response_model=ApiResponse[DatasetSummary])
def get_dataset(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Return a single dataset summary."""
    return ApiResponse.ok(DatasetService(db).get_summary(dataset_id, current_user.id))


@router.get("/{dataset_id}/preview", response_model=ApiResponse[DatasetPreview])
def preview_dataset(
    dataset_id: int,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    rows: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Return a page of rows from a dataset."""
    return ApiResponse.ok(DatasetService(db).preview(dataset_id, current_user.id, rows, offset))


@router.delete("/{dataset_id}", response_model=ApiResponse[None])
def delete_dataset(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Permanently delete a dataset and all its analysis."""
    DatasetService(db).delete(dataset_id, current_user.id)
    return ApiResponse.ok(message="Dataset deleted.")


@router.post("/{dataset_id}/approval", response_model=ApiResponse[DatasetSummary])
def set_approval(
    dataset_id: int,
    payload: ApprovalRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Approve or reject a dataset that is pending human review."""
    summary = DatasetService(db).set_approval(dataset_id, current_user.id, payload.approved, payload.note)
    message = "Dataset approved." if payload.approved else "Dataset rejected."
    return ApiResponse.ok(summary, message=message)
