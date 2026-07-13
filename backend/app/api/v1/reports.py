"""Report generation and download endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import CurrentUser
from app.schemas.chat import ReportRequest, ReportResponse
from app.schemas.common import ApiResponse
from app.services.report_service import ReportService

router = APIRouter(tags=["Reports"])

_MEDIA = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "json": "application/json",
    "csv": "text/csv",
}


@router.post("/datasets/{dataset_id}/reports", response_model=ApiResponse[ReportResponse])
def generate_report(
    dataset_id: int,
    payload: ReportRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Generate a downloadable report artifact for a dataset."""
    record = ReportService(db).generate(dataset_id, current_user.id, payload.report_type)
    return ApiResponse.ok(record, message="Report generated.")


@router.get("/reports/{report_id}/download")
def download_report(report_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Download a previously generated report."""
    record = ReportService(db).get_record(report_id, current_user.id)
    path = Path(record.file_path)
    return FileResponse(
        path,
        media_type=_MEDIA.get(record.report_type, "application/octet-stream"),
        filename=path.name,
    )
