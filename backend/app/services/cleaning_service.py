"""Cleaning service: apply cleaning and produce a before/after comparison."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.core.engines.cleaner import Cleaner
from app.core.engines.profiler import Profiler
from app.core.engines.quality_checks import QualityEngine
from app.core.engines.scorer import Scorer
from app.core.storage import get_storage
from app.exceptions.base import NotFoundException
from app.schemas.dataset import DatasetPreview
from app.models.dataset import Dataset
from app.repositories.analysis_repository import AnalysisHistoryRepository
from app.repositories.cleaning_repository import CleaningRepository
from app.schemas.quality import (
    CleaningOpResponse,
    CleaningResultResponse,
    CompareMetrics,
)
from app.services.base import BaseService, DatasetContextMixin
from app.services.dataset_service import DatasetService


class CleaningService(BaseService, DatasetContextMixin):
    """Runs one-click cleaning and persists the cleaned dataset."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.profiler = Profiler()
        self.cleaner = Cleaner()
        self.quality = QualityEngine()
        self.scorer = Scorer()
        self.dataset_service = DatasetService(db)
        self.history = AnalysisHistoryRepository(db)
        self.cleaning_reports = CleaningRepository(db)
        self.storage = get_storage()

    def clean(self, dataset_id: int, user_id: int) -> CleaningResultResponse:
        """Clean a dataset, persist the result and return a comparison."""
        source = self._load_owned_dataset(dataset_id, user_id)
        df = self._read_frame(source)

        before_profile = self.profiler.profile(df)
        before_score = self.scorer.score(self.quality.run(df, before_profile), before_profile)

        result = self.cleaner.clean(df, before_profile)
        cleaned_df = result.df

        after_profile = self.profiler.profile(cleaned_df)
        after_score = self.scorer.score(self.quality.run(cleaned_df, after_profile), after_profile)

        cleaned_dataset = self.dataset_service.save_cleaned(source, cleaned_df, user_id)

        operations = [
            {"op": o.op, "column": o.column, "rows_affected": o.rows_affected,
             "detail": o.detail, "rows": o.rows}
            for o in result.operations
        ]
        comparison = [
            m.model_dump()
            for m in self._compare(
                df, cleaned_df, before_profile, after_profile,
                before_score, after_score, result.operations,
            )
        ]

        # Persist so the result survives navigation and reloads.
        self.cleaning_reports.create(
            dataset_id=source.id, user_id=user_id, cleaned_dataset_id=cleaned_dataset.id,
            operations=operations, comparison=comparison,
            before_score=before_score.overall, after_score=after_score.overall, created_by=user_id,
        )
        self.history.create(
            user_id=user_id, dataset_id=source.id, action="clean",
            summary=f"Score {before_score.overall} -> {after_score.overall}",
            payload={"ops": len(result.operations)}, created_by=user_id,
        )
        self.db.commit()

        return CleaningResultResponse(
            cleaned_dataset_id=cleaned_dataset.id,
            operations=[CleaningOpResponse(**o) for o in operations],
            comparison=[CompareMetrics(**c) for c in comparison],
        )

    def get_latest(self, dataset_id: int, user_id: int) -> CleaningResultResponse | None:
        """Return the most recent persisted cleaning result, if any."""
        self._load_owned_dataset(dataset_id, user_id)
        report = self.cleaning_reports.latest_for_dataset(dataset_id)
        if report is None:
            return None
        return CleaningResultResponse(
            cleaned_dataset_id=report.cleaned_dataset_id,
            operations=[CleaningOpResponse(**o) for o in report.operations],
            comparison=[CompareMetrics(**c) for c in report.comparison],
        )

    def get_op_affected(self, dataset_id: int, op_index: int, user_id: int) -> "DatasetPreview":
        """Return the ORIGINAL rows a specific cleaning operation touched."""
        source = self._load_owned_dataset(dataset_id, user_id)
        report = self.cleaning_reports.latest_for_dataset(dataset_id)
        if report is None or not (0 <= op_index < len(report.operations)):
            raise NotFoundException("Cleaning operation not found.")
        op = report.operations[op_index]
        rows: list[int] = op.get("rows") or []

        df = self._read_frame(source)
        valid = [i for i in rows if 0 <= i < len(df)]
        subset = df.iloc[valid]

        # Surface the operated-on column first for quick scanning.
        column = op.get("column")
        cols = list(df.columns)
        if column in cols:
            cols = [column] + [c for c in cols if c != column]
            subset = subset[cols]

        subset = subset.astype(object).where(pd.notna(subset), None)
        return DatasetPreview(
            columns=[str(c) for c in subset.columns],
            rows=subset.to_dict(orient="records"),
            total_rows=int(op.get("rows_affected", len(valid))),
        )

    def build_comparison_workbook(self, dataset_id: int, user_id: int) -> tuple[Path, str]:
        """Build an Excel workbook with Original + Cleaned sheets for download."""
        source = self._load_owned_dataset(dataset_id, user_id)
        report = self.cleaning_reports.latest_for_dataset(dataset_id)
        if report is None:
            raise NotFoundException("Run cleaning before downloading the comparison.")
        cleaned = self.db.get(Dataset, report.cleaned_dataset_id)
        if cleaned is None:
            raise NotFoundException("Cleaned dataset no longer exists.")

        original_df = self._read_frame(source)
        cleaned_df = pd.read_parquet(cleaned.parquet_path)

        filename = f"{source.name}_comparison.xlsx"
        path = self.storage.report_path(f"{dataset_id}_comparison.xlsx")
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            original_df.to_excel(writer, sheet_name="Original", index=False)
            cleaned_df.to_excel(writer, sheet_name="Cleaned", index=False)
        return path, filename

    def _compare(self, before_df, after_df, bp, ap, bs, ascore, operations) -> list[CompareMetrics]:
        def null_pct(profile) -> float:
            if not profile.columns:
                return 0.0
            return round(sum(c.null_pct for c in profile.columns) / len(profile.columns), 2)

        # Duplicates the cleaner actually removed (catches rows that only became
        # identical after trimming/standardizing) — a plain exact-match count on
        # the original frame can read 0 while a row was still deduped away.
        removed_dupes = sum(o.rows_affected for o in operations if o.op == "remove_duplicates")

        return [
            CompareMetrics(label="Quality Score", before=bs.overall, after=ascore.overall),
            CompareMetrics(label="Rows", before=len(before_df), after=len(after_df)),
            CompareMetrics(label="Columns", before=before_df.shape[1], after=after_df.shape[1]),
            CompareMetrics(
                label="Duplicate Rows",
                before=max(bs.duplicate_rows, removed_dupes + ascore.duplicate_rows),
                after=ascore.duplicate_rows,
            ),
            CompareMetrics(label="Avg Null %", before=null_pct(bp), after=null_pct(ap)),
            CompareMetrics(
                label="Memory (KB)",
                before=round(before_df.memory_usage(deep=True).sum() / 1024, 1),
                after=round(after_df.memory_usage(deep=True).sum() / 1024, 1),
            ),
        ]
