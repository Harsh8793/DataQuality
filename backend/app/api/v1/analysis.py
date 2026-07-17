"""Analysis endpoints: profiling, quality analysis (sync + SSE), cleaning."""

from __future__ import annotations

import json
import queue
import threading
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database.session import SessionLocal, get_db
from app.dependencies.auth import CurrentUser, get_current_user
from app.models.user import User
from app.schemas.ai import (
    ExclusionActionResponse,
    ExclusionListResponse,
    ExclusionRequest,
    FixAllResponse,
    FixListResponse,
    IssueFixResponse,
    UndoFixResponse,
    ValidationActionResponse,
    ValidationCreateRequest,
    ValidationListResponse,
    ValidationProposal,
    ValidationProposeRequest,
)
from app.schemas.common import ApiResponse
from app.services.custom_validation_service import CustomValidationService
from app.schemas.dataset import ColumnProfileResponse, DatasetPreview
from app.schemas.quality import CleaningResultResponse, QualityReportResponse
from app.services.analysis_service import AnalysisService
from app.services.cleaning_service import CleaningService

logger = get_logger(__name__)
router = APIRouter(prefix="/datasets", tags=["Analysis"])

_SENTINEL = object()


@router.post("/{dataset_id}/analyze", response_model=ApiResponse[QualityReportResponse])
def analyze(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Run the full analysis pipeline synchronously and return the report."""
    report = AnalysisService(db).analyze(dataset_id, current_user.id)
    return ApiResponse.ok(report, message="Analysis complete.")


@router.get("/{dataset_id}/analyze/stream")
def analyze_stream(dataset_id: int, current_user: User = Depends(get_current_user)):
    """Run analysis in the background and stream live agent progress via SSE."""
    events: queue.Queue = queue.Queue()

    def emit(event: str, payload: dict) -> None:
        events.put((event, payload))

    def worker() -> None:
        db = SessionLocal()
        try:
            report = AnalysisService(db).analyze(dataset_id, current_user.id, emit=emit)
            events.put(("result", report.model_dump(mode="json")))
        except Exception as exc:  # noqa: BLE001 - surface as an SSE error frame
            logger.exception("Streamed analysis failed: %s", exc)
            events.put(("error", {"message": str(exc)}))
        finally:
            db.close()
            events.put((_SENTINEL, None))

    threading.Thread(target=worker, daemon=True).start()

    def event_stream():
        while True:
            event, payload = events.get()
            if event is _SENTINEL:
                break
            yield f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{dataset_id}/profile", response_model=ApiResponse[list[ColumnProfileResponse]])
def get_profile(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Return column profiles for a dataset (profiled on demand if needed)."""
    columns = AnalysisService(db).get_profile(dataset_id, current_user.id)
    return ApiResponse.ok([ColumnProfileResponse.model_validate(c) for c in columns])


@router.get("/{dataset_id}/quality", response_model=ApiResponse[QualityReportResponse])
def get_quality(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Return the latest quality report, running analysis if none exists yet."""
    service = AnalysisService(db)
    report = service.get_latest(dataset_id, current_user.id)
    if report is None:
        report = service.analyze(dataset_id, current_user.id)
    return ApiResponse.ok(report)


@router.post("/{dataset_id}/clean", response_model=ApiResponse[CleaningResultResponse])
def clean(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Run one-click cleaning and return the before/after comparison."""
    result = CleaningService(db).clean(dataset_id, current_user.id)
    return ApiResponse.ok(result, message="Dataset cleaned.")


@router.get("/{dataset_id}/clean", response_model=ApiResponse[CleaningResultResponse | None])
def get_clean_result(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Return the most recent cleaning result for a dataset (or null)."""
    return ApiResponse.ok(CleaningService(db).get_latest(dataset_id, current_user.id))


@router.get("/{dataset_id}/clean/operations/{op_index}/affected", response_model=ApiResponse[DatasetPreview])
def clean_op_affected(
    dataset_id: int,
    op_index: int,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Return the original rows a specific cleaning operation touched."""
    return ApiResponse.ok(CleaningService(db).get_op_affected(dataset_id, op_index, current_user.id))


@router.get("/{dataset_id}/clean/download")
def download_clean_comparison(
    dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]
):
    """Download an Excel workbook with Original + Cleaned sheets."""
    path, filename = CleaningService(db).build_comparison_workbook(dataset_id, current_user.id)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )


@router.post("/{dataset_id}/quality/issues/{issue_id}/fix", response_model=ApiResponse[IssueFixResponse])
def fix_issue(
    dataset_id: int,
    issue_id: int,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Apply the targeted one-click fix for a single quality issue."""
    result = AnalysisService(db).fix_issue(dataset_id, issue_id, current_user.id)
    return ApiResponse.ok(IssueFixResponse(**result), message=result["detail"])


@router.get("/{dataset_id}/quality/issues/{issue_id}/affected", response_model=ApiResponse[DatasetPreview])
def affected_rows(
    dataset_id: int,
    issue_id: int,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    all_columns: bool = False,
):
    """Return the rows that triggered a specific quality issue."""
    result = AnalysisService(db).get_affected_rows(
        dataset_id, issue_id, current_user.id, all_columns=all_columns
    )
    return ApiResponse.ok(result)


@router.post("/{dataset_id}/quality/fix-all", response_model=ApiResponse[FixAllResponse])
def fix_all_issues(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Apply every fixable issue's targeted fix as one undoable batch."""
    result = AnalysisService(db).fix_all(dataset_id, current_user.id)
    return ApiResponse.ok(FixAllResponse(**result), message=f"Applied {result['applied']} fixes.")


@router.get("/{dataset_id}/quality/fixes", response_model=ApiResponse[FixListResponse])
def list_fixes(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Return the audit trail of applied fixes with before/after samples."""
    return ApiResponse.ok(FixListResponse(**AnalysisService(db).list_fixes(dataset_id, current_user.id)))


@router.post("/{dataset_id}/quality/fixes/undo", response_model=ApiResponse[UndoFixResponse])
def undo_fixes(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Undo the most recent fix batch (restores the pre-fix snapshot)."""
    result = AnalysisService(db).undo_fixes(dataset_id, current_user.id)
    return ApiResponse.ok(UndoFixResponse(**result), message="Fixes undone.")


@router.post("/{dataset_id}/quality/validations/propose", response_model=ApiResponse[ValidationProposal])
def propose_validation(
    dataset_id: int,
    payload: ValidationProposeRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """AI interprets a natural-language rule into a validation preview for approval."""
    proposal = CustomValidationService(db).propose(dataset_id, current_user.id, payload.prompt)
    return ApiResponse.ok(proposal)


@router.post("/{dataset_id}/quality/validations", response_model=ApiResponse[ValidationActionResponse])
def add_validation(
    dataset_id: int,
    payload: ValidationCreateRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Approve and persist a custom validation, then re-analyze."""
    CustomValidationService(db).create(dataset_id, current_user.id, payload)
    report = AnalysisService(db).analyze(dataset_id, current_user.id)
    validations = CustomValidationService(db).list(dataset_id, current_user.id)
    return ApiResponse.ok(
        ValidationActionResponse(validations=validations, report=report),
        message="Validation added.",
    )


@router.get("/{dataset_id}/quality/validations", response_model=ApiResponse[ValidationListResponse])
def list_validations(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Return the custom validations defined for a dataset."""
    return ApiResponse.ok(
        ValidationListResponse(validations=CustomValidationService(db).list(dataset_id, current_user.id))
    )


@router.delete("/{dataset_id}/quality/validations/{validation_id}", response_model=ApiResponse[ValidationActionResponse])
def delete_validation(
    dataset_id: int,
    validation_id: int,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Delete a custom validation, then re-analyze."""
    CustomValidationService(db).delete(dataset_id, validation_id, current_user.id)
    report = AnalysisService(db).analyze(dataset_id, current_user.id)
    validations = CustomValidationService(db).list(dataset_id, current_user.id)
    return ApiResponse.ok(
        ValidationActionResponse(validations=validations, report=report),
        message="Validation deleted.",
    )


@router.get("/{dataset_id}/quality/exclusions", response_model=ApiResponse[ExclusionListResponse])
def list_exclusions(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Return validations the user has excluded from analysis."""
    return ApiResponse.ok(ExclusionListResponse(**AnalysisService(db).list_exclusions(dataset_id, current_user.id)))


@router.post("/{dataset_id}/quality/exclusions", response_model=ApiResponse[ExclusionActionResponse])
def add_exclusion(
    dataset_id: int,
    payload: ExclusionRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Exclude a validation so it no longer appears or affects the score."""
    result = AnalysisService(db).add_exclusion(dataset_id, current_user.id, payload.check_key, payload.column_name)
    return ApiResponse.ok(ExclusionActionResponse(**result), message="Validation excluded.")


@router.post("/{dataset_id}/quality/exclusions/remove", response_model=ApiResponse[ExclusionActionResponse])
def remove_exclusion(
    dataset_id: int,
    payload: ExclusionRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Re-include a previously excluded validation."""
    result = AnalysisService(db).remove_exclusion(dataset_id, current_user.id, payload.check_key, payload.column_name)
    return ApiResponse.ok(ExclusionActionResponse(**result), message="Validation re-included.")
