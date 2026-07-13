"""Dataset service: upload, listing, preview and parquet materialization."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.upload_agent import UploadAgent
from app.config import get_settings
from app.core.storage import get_storage
from app.exceptions.base import BadRequestException, UnsupportedFormatException
from app.models.analysis import AnalysisHistory, QualityIssue, QualityReport
from app.models.chat import ChatMessage, ChatSession
from app.models.dataset import Dataset, DatasetColumn, UploadedFile
from app.models.edit import DatasetEdit
from app.models.exclusion import IssueExclusion
from app.models.fixes import FixBatch, IssueFix
from app.models.governance import GovernanceReport
from app.models.report import DashboardHistory, GeneratedReport
from app.repositories.dataset_repository import (
    DatasetColumnRepository,
    DatasetRepository,
    UploadedFileRepository,
)
from app.schemas.dataset import DatasetPreview, DatasetSummary
from app.services.base import BaseService, DatasetContextMixin


class DatasetService(BaseService, DatasetContextMixin):
    """Handles the upload pipeline and dataset retrieval."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.settings = get_settings()
        self.storage = get_storage()
        self.datasets = DatasetRepository(db)
        self.files = UploadedFileRepository(db)
        self.columns = DatasetColumnRepository(db)
        self.upload_agent = UploadAgent()

    # ---- upload ------------------------------------------------------- #
    def upload(self, user_id: str, filename: str, content: bytes) -> DatasetSummary:
        """Validate, load, persist as parquet and register a new dataset."""
        ext = self._validate(filename, content)

        # Load into a DataFrame (encoding/delimiter detection handled by agent).
        load_result = self.upload_agent.load(content, ext)
        df = load_result.df
        if df.empty:
            raise BadRequestException("The uploaded file contains no data rows.")
        df = self._normalize_columns(df)

        # Persist raw file for provenance, then the parquet cache.
        stored_name, stored_path = self.storage.save_upload(filename, content)
        uploaded = self.files.create(
            user_id=user_id,
            original_filename=filename,
            stored_filename=stored_name,
            extension=ext,
            size_bytes=len(content),
            storage_path=str(stored_path),
            created_by=user_id,
        )

        dataset = self.datasets.create(
            user_id=user_id,
            uploaded_file_id=uploaded.id,
            name=filename.rsplit(".", 1)[0],
            file_format=load_result.file_format,
            encoding=load_result.encoding,
            delimiter=load_result.delimiter,
            row_count=int(len(df)),
            col_count=int(df.shape[1]),
            file_size_bytes=len(content),
            memory_bytes=int(df.memory_usage(deep=True).sum()),
            parquet_path="",  # set after we know the id
            status="uploaded",
            created_by=user_id,
        )
        parquet_path = self.storage.parquet_path(dataset.id)
        df.to_parquet(parquet_path, index=False)
        self.datasets.update(dataset, parquet_path=str(parquet_path))
        self.db.commit()

        self.logger.info("Uploaded dataset %s (%d x %d)", dataset.id, len(df), df.shape[1])
        return DatasetSummary.model_validate(dataset)

    # ---- retrieval ---------------------------------------------------- #
    def list(self, user_id: str, limit: int, offset: int) -> tuple[list[DatasetSummary], int]:
        """Return a page of the user's datasets and the total count."""
        items = self.datasets.list(user_id=user_id, limit=limit, offset=offset)
        total = self.datasets.count(user_id=user_id)
        return [DatasetSummary.model_validate(d) for d in items], total

    def get_summary(self, dataset_id: str, user_id: str) -> DatasetSummary:
        """Return a single dataset summary."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        return DatasetSummary.model_validate(dataset)

    def preview(self, dataset_id: str, user_id: str, rows: int = 50, offset: int = 0) -> DatasetPreview:
        """Return a page of ``rows`` rows starting at ``offset``."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        df = self._read_frame(dataset)
        page = df.iloc[offset : offset + rows]
        page = page.astype(object).where(pd.notna(page), None)
        return DatasetPreview(
            columns=[str(c) for c in df.columns],
            rows=page.to_dict(orient="records"),
            total_rows=int(len(df)),
        )

    def delete(self, dataset_id: int, user_id: int) -> None:
        """Hard-delete a dataset: remove all related rows and files from disk.

        Cleaned child datasets (``parent_id == dataset_id``) are removed too, so
        no orphaned rows or parquet files are left behind.
        """
        dataset = self._load_owned_dataset(dataset_id, user_id)

        # Remove any cleaned children first, then the dataset itself.
        children = self.db.scalars(
            select(Dataset).where(Dataset.parent_id == dataset.id)
        ).all()
        for child in children:
            self._hard_delete_one(child)
        self._hard_delete_one(dataset)

        self.db.commit()
        self.logger.info("Hard-deleted dataset %s (+%d cleaned children)", dataset_id, len(children))

    def _hard_delete_one(self, dataset: Dataset) -> None:
        """Delete one dataset's rows across all tables and its files on disk."""
        did = dataset.id

        # Report files + rows.
        reports = self.db.scalars(select(GeneratedReport).where(GeneratedReport.dataset_id == did)).all()
        report_paths = [r.file_path for r in reports]

        # Quality issues are keyed by report id.
        report_ids = list(self.db.scalars(select(QualityReport.id).where(QualityReport.dataset_id == did)).all())
        if report_ids:
            self.db.execute(sa_delete(QualityIssue).where(QualityIssue.report_id.in_(report_ids)))
        self.db.execute(sa_delete(QualityReport).where(QualityReport.dataset_id == did))

        # Chat messages are keyed by session id.
        session_ids = list(self.db.scalars(select(ChatSession.id).where(ChatSession.dataset_id == did)).all())
        if session_ids:
            self.db.execute(sa_delete(ChatMessage).where(ChatMessage.session_id.in_(session_ids)))
        self.db.execute(sa_delete(ChatSession).where(ChatSession.dataset_id == did))

        self.db.execute(sa_delete(DatasetColumn).where(DatasetColumn.dataset_id == did))
        self.db.execute(sa_delete(DatasetEdit).where(DatasetEdit.dataset_id == did))
        # Fix audit rows + their parquet snapshots on disk.
        snapshots = list(self.db.scalars(
            select(FixBatch.snapshot_path).where(FixBatch.dataset_id == did)
        ).all())
        self.db.execute(sa_delete(IssueFix).where(IssueFix.dataset_id == did))
        self.db.execute(sa_delete(FixBatch).where(FixBatch.dataset_id == did))
        self.db.execute(sa_delete(IssueExclusion).where(IssueExclusion.dataset_id == did))
        for snap in snapshots:
            self._safe_unlink(snap)
        self.db.execute(sa_delete(GovernanceReport).where(GovernanceReport.dataset_id == did))
        self.db.execute(sa_delete(DashboardHistory).where(DashboardHistory.dataset_id == did))
        self.db.execute(sa_delete(GeneratedReport).where(GeneratedReport.dataset_id == did))
        self.db.execute(sa_delete(AnalysisHistory).where(AnalysisHistory.dataset_id == did))

        uploaded_file_id = dataset.uploaded_file_id
        parquet_path = dataset.parquet_path
        self.db.execute(sa_delete(Dataset).where(Dataset.id == did))

        # Only delete the uploaded source file if no other dataset still uses it
        # (a cleaned dataset shares its parent's uploaded_file_id).
        if uploaded_file_id is not None:
            remaining = self.db.scalar(
                select(func.count()).select_from(Dataset).where(Dataset.uploaded_file_id == uploaded_file_id)
            )
            if not remaining:
                uploaded = self.db.get(UploadedFile, uploaded_file_id)
                if uploaded:
                    self._safe_unlink(uploaded.storage_path)
                    self.db.execute(sa_delete(UploadedFile).where(UploadedFile.id == uploaded_file_id))

        # Remove files on disk.
        self._safe_unlink(parquet_path)
        for path in report_paths:
            self._safe_unlink(path)

    def _safe_unlink(self, path: str | None) -> None:
        """Delete a file if it exists, ignoring errors."""
        if not path:
            return
        try:
            Path(path).unlink(missing_ok=True)
        except OSError as exc:  # noqa: BLE001 - file cleanup must never block deletion
            self.logger.warning("Could not delete file %s: %s", path, exc)

    # ---- helpers ------------------------------------------------------ #
    def set_approval(self, dataset_id: int, user_id: int, approved: bool, note: str | None) -> DatasetSummary:
        """Approve or reject a dataset that is pending human review."""
        from datetime import datetime, timezone

        from app.constants.enums import ApprovalStatus

        dataset = self._load_owned_dataset(dataset_id, user_id)
        self.datasets.update(
            dataset,
            approval_status=ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED,
            approval_note=note,
            reviewed_by=user_id,
            reviewed_at=datetime.now(timezone.utc),
        )
        self.db.commit()
        self.logger.info("Dataset %s %s by user %s", dataset_id, dataset.approval_status, user_id)
        return DatasetSummary.model_validate(dataset)

    def _validate(self, filename: str, content: bytes) -> str:
        if "." not in filename:
            raise UnsupportedFormatException("File has no extension.")
        ext = filename.rsplit(".", 1)[1].lower()
        if ext not in self.settings.allowed_extension_set:
            raise UnsupportedFormatException(f"Unsupported extension '.{ext}'.")
        if len(content) > self.settings.max_upload_bytes:
            raise BadRequestException(f"File exceeds the {self.settings.max_upload_mb} MB limit.")
        if not content:
            raise BadRequestException("The uploaded file is empty.")
        return ext

    @staticmethod
    def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Ensure column names are unique, stripped strings (parquet-safe)."""
        df = df.copy()
        seen: dict[str, int] = {}
        new_cols = []
        for col in df.columns:
            name = str(col).strip() or "column"
            if name in seen:
                seen[name] += 1
                name = f"{name}_{seen[name]}"
            else:
                seen[name] = 0
            new_cols.append(name)
        df.columns = new_cols
        return df

    def save_cleaned(self, source: Dataset, df: pd.DataFrame, user_id: str) -> Dataset:
        """Persist a cleaned DataFrame as a new child dataset."""
        dataset = self.datasets.create(
            user_id=user_id,
            uploaded_file_id=source.uploaded_file_id,
            parent_id=source.id,
            name=f"{source.name} (cleaned)",
            file_format=source.file_format,
            encoding=source.encoding,
            delimiter=source.delimiter,
            row_count=int(len(df)),
            col_count=int(df.shape[1]),
            file_size_bytes=source.file_size_bytes,
            memory_bytes=int(df.memory_usage(deep=True).sum()),
            parquet_path="",
            status="cleaned",
            is_cleaned=True,
            created_by=user_id,
        )
        parquet_path = self.storage.parquet_path(dataset.id)
        df.to_parquet(parquet_path, index=False)
        self.datasets.update(dataset, parquet_path=str(parquet_path))
        return dataset
