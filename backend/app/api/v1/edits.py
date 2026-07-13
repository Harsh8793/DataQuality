"""Manual data-editing endpoints: apply cell edits, undo, history."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import CurrentUser
from app.schemas.ai import (
    ApplyEditsRequest,
    ApplyEditsResponse,
    EditHistoryResponse,
    UndoEditResponse,
)
from app.schemas.common import ApiResponse
from app.schemas.dataset import RowQueryRequest, RowQueryResponse
from app.services.edit_service import EditService

router = APIRouter(prefix="/datasets", tags=["Data Editing"])


@router.post("/{dataset_id}/edits", response_model=ApiResponse[ApplyEditsResponse])
def apply_edits(
    dataset_id: int,
    payload: ApplyEditsRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Apply a batch of manual cell edits, then re-run the quality analysis."""
    result = EditService(db).apply(dataset_id, current_user.id, payload.edits)
    return ApiResponse.ok(result, message=f"Applied {result.applied} edit(s) and re-analyzed.")


@router.post("/{dataset_id}/edits/undo", response_model=ApiResponse[UndoEditResponse])
def undo_edits(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Undo the most recent edit batch, then re-run the quality analysis."""
    result = EditService(db).undo_last(dataset_id, current_user.id)
    return ApiResponse.ok(result, message=f"Undid {result.undone} edit(s) and re-analyzed.")


@router.get("/{dataset_id}/edits", response_model=ApiResponse[EditHistoryResponse])
def edit_history(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Return the undoable edit history for a dataset."""
    return ApiResponse.ok(EditService(db).get_history(dataset_id, current_user.id))


@router.post("/{dataset_id}/rows/query", response_model=ApiResponse[RowQueryResponse])
def query_rows(
    dataset_id: int,
    payload: RowQueryRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Return a filtered, paginated slice of rows with their true row indices."""
    result = EditService(db).query_rows(
        dataset_id, current_user.id,
        filter_column=payload.filter_column, filter_op=payload.filter_op,
        filter_value=payload.filter_value, limit=payload.limit, offset=payload.offset,
    )
    return ApiResponse.ok(result)
