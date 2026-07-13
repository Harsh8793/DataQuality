"""Analysis service: run the agent pipeline and persist all results."""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import AgentContext
from app.agents.governance_agent import GovernanceResult
from app.agents.orchestrator import get_coordinator
from app.constants.enums import APPROVAL_THRESHOLD, ApprovalStatus
from app.core.engines.affected import affected_mask
from app.core.engines.explanations import explain_issue
from app.core.engines.fixer import FIXABLE_CHECKS, UnfixableIssueError, apply_fix
from app.core.engines.scorer import Scorer
from app.core.engines.profiler import DatasetProfile
from app.core.engines.scorer import QualityScore
from app.exceptions.base import BadRequestException, NotFoundException
from app.models.dataset import Dataset
from app.models.fixes import IssueFix
from app.models.analysis import QualityReport
from app.repositories.analysis_repository import (
    AnalysisHistoryRepository,
    QualityIssueRepository,
    QualityReportRepository,
)
from app.repositories.dataset_repository import DatasetColumnRepository, DatasetRepository
from app.repositories.exclusion_repository import ExclusionRepository
from app.repositories.fix_repository import FixBatchRepository, IssueFixRepository
from app.repositories.governance_repository import GovernanceRepository
from app.schemas.ai import FixRecord
from app.schemas.dataset import DatasetPreview
from app.schemas.quality import COLUMN_LEVEL_CHECKS, QualityIssueResponse, QualityReportResponse
from app.services.base import BaseService, DatasetContextMixin

# Sample cap for the before/after change log stored with each fix.
_MAX_CHANGES = 200


class AnalysisService(BaseService, DatasetContextMixin):
    """Coordinates the analysis pipeline and persistence."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.datasets = DatasetRepository(db)
        self.columns = DatasetColumnRepository(db)
        self.reports = QualityReportRepository(db)
        self.issues = QualityIssueRepository(db)
        self.governance = GovernanceRepository(db)
        self.history = AnalysisHistoryRepository(db)
        self.fix_batches = FixBatchRepository(db)
        self.fixes = IssueFixRepository(db)
        self.exclusions = ExclusionRepository(db)
        self.coordinator = get_coordinator()

    def analyze(
        self,
        dataset_id: str,
        user_id: str,
        emit: Callable[[str, dict], None] | None = None,
    ) -> QualityReportResponse:
        """Run the full pipeline for a dataset and persist the results."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        ctx = self._build_context(dataset)
        ctx._emit = emit
        ctx.meta["is_cleaned"] = dataset.is_cleaned

        started = time.perf_counter()
        self.coordinator.run_analysis(ctx)
        duration_ms = int((time.perf_counter() - started) * 1000)

        # Drop any user-excluded validations before scoring/persisting so they
        # neither appear as issues nor lower the quality score.
        self._apply_exclusions(dataset.id, ctx)

        governance: GovernanceResult | None = ctx.meta.get("governance")
        report = self._persist(dataset, ctx, governance, duration_ms, user_id)

        # Human approval gate: poor-quality datasets need review before use.
        approval = (
            ApprovalStatus.APPROVED
            if report.overall_score >= APPROVAL_THRESHOLD
            else ApprovalStatus.PENDING
        )
        self.datasets.update(dataset, status="analyzed", approval_status=approval)
        self.history.create(
            user_id=user_id, dataset_id=dataset.id, action="analyze",
            summary=f"Quality score {report.overall_score}/100",
            payload={"issues": report.total_issues}, created_by=user_id,
        )
        self.db.commit()
        return self._to_response(report, dataset.id)

    # ---- persistence -------------------------------------------------- #
    def _persist(self, dataset: Dataset, ctx: AgentContext, governance, duration_ms, user_id):
        assert ctx.profile is not None and ctx.score is not None
        self._persist_columns(dataset, ctx.profile, governance, user_id)
        report = self._persist_report(dataset, ctx.score, duration_ms, user_id)
        self._persist_issues(report.id, ctx, user_id)
        if governance is not None:
            self._persist_governance(dataset, governance, user_id)
        return report

    def _persist_columns(self, dataset, profile: DatasetProfile, governance, user_id) -> None:
        self.columns.delete_for_dataset(dataset.id)
        meta_by_name = {}
        if governance is not None:
            meta_by_name = {m.get("name"): m for m in governance.column_metadata}
        for col in profile.columns:
            meta = meta_by_name.get(col.name, {})
            self.columns.create(
                dataset_id=dataset.id, name=col.name, ordinal=col.ordinal,
                physical_type=col.physical_type, semantic_type=col.semantic_type,
                null_count=col.null_count, null_pct=col.null_pct,
                distinct_count=col.distinct_count, cardinality_ratio=col.cardinality_ratio,
                min_val=col.min_val, max_val=col.max_val, mean_val=col.mean_val,
                std_val=col.std_val, sample_values=col.sample_values,
                business_name=meta.get("business_name"), description=meta.get("description"),
                sensitivity=meta.get("sensitivity"), is_pii=bool(meta.get("is_pii", False)),
                created_by=user_id,
            )

    def _persist_report(self, dataset, score: QualityScore, duration_ms, user_id):
        dims = score.dimensions
        return self.reports.create(
            dataset_id=dataset.id, user_id=user_id,
            overall_score=score.overall,
            completeness=dims.get("completeness", 0), accuracy=dims.get("accuracy", 0),
            consistency=dims.get("consistency", 0), uniqueness=dims.get("uniqueness", 0),
            validity=dims.get("validity", 0), integrity=dims.get("integrity", 0),
            duplicate_rows=score.duplicate_rows, total_issues=score.total_issues,
            duration_ms=duration_ms, created_by=user_id,
        )

    def _persist_issues(self, report_id: str, ctx: AgentContext, user_id) -> None:
        # Explanations are generated deterministically per issue so the column
        # and count are ALWAYS correct. AI explainers are keyed by check type
        # only, so they'd repeat one column/number across every issue.
        total = ctx.profile.row_count if ctx.profile else 0
        for f in ctx.findings:
            # For duplicate columns, sample[0] holds the column it duplicates.
            ref = f.sample[0] if f.check_key == "duplicate_columns" and f.sample else None
            ex = explain_issue(f.check_key, f.column_name, f.count, total, ref_column=ref)
            self.issues.create(
                report_id=report_id, column_name=f.column_name, check_key=f.check_key,
                dimension=f.dimension, severity=f.severity, count=f.count, sample=f.sample,
                problem=self._issue_title(f.check_key, f.column_name), why=ex["why"],
                business_impact=ex["business_impact"], recommended_fix=ex["recommended_fix"],
                confidence=ex["confidence"], created_by=user_id,
            )

    @staticmethod
    def _is_fixable(check_key: str, count: int, total_rows: int) -> bool:
        """Whether a one-click fix helps. A 100%-empty column can't be imputed —
        there's nothing to fill from, so we suggest dropping it instead."""
        if check_key not in FIXABLE_CHECKS:
            return False
        if check_key in {"missing_values", "blank_strings"} and total_rows and count >= total_rows:
            return False
        return True

    # Plain-language issue titles. The column is shown as its own chip in the UI,
    # so the title deliberately omits it (no "… in ADDN_TYPE_8" repetition).
    _TITLES = {
        "missing_values": "Missing values",
        "blank_strings": "Blank values",
        "whitespace": "Untrimmed whitespace",
        "duplicate_rows": "Duplicate rows",
        "duplicate_ids": "Duplicate identifiers",
        "invalid_email": "Invalid emails",
        "invalid_phone": "Invalid phone numbers",
        "invalid_url": "Invalid URLs",
        "invalid_date": "Invalid dates",
        "negative_values": "Negative values",
        "outliers": "Outliers",
        "case_inconsistency": "Inconsistent casing",
        "mixed_types": "Mixed data types",
        "constant_column": "Same value in every row",
        "duplicate_columns": "Duplicate of another column",
        "high_cardinality": "Almost all values unique",
        "low_cardinality": "Very few distinct values",
        "unicode_issues": "Corrupted characters",
        "datatype_mismatch": "Wrong data type",
        "empty_dataset": "Empty dataset",
    }

    @classmethod
    def _issue_title(cls, check_key: str, column: str | None) -> str:
        """Return a plain-language title for the issue (column shown separately)."""
        label = cls._TITLES.get(check_key)
        if label:
            return label
        label = check_key.replace("_", " ")
        return label[:1].upper() + label[1:]

    def _persist_governance(self, dataset, gov: GovernanceResult, user_id) -> None:
        self.governance.create(
            dataset_id=dataset.id, user_id=user_id,
            classification=gov.classification, pii_columns=gov.pii_columns,
            rationale=gov.rationale, ingestion_tier=gov.ingestion_tier,
            tier_rationale=gov.tier_rationale, created_by=user_id,
        )

    # ---- read --------------------------------------------------------- #
    def get_profile(self, dataset_id: int, user_id: int) -> list:
        """Return persisted column profiles, profiling on the fly if missing.

        Freshly uploaded datasets have no persisted columns until the full
        analysis runs — profile deterministically here so the Overview tab
        always has a column profile to show.
        """
        dataset = self._load_owned_dataset(dataset_id, user_id)
        columns = self.columns.list_for_dataset(dataset_id)
        if columns:
            return columns

        from app.agents.profiling_agent import ProfilingAgent

        ctx = self._build_context(dataset)
        ProfilingAgent().run(ctx)
        if ctx.profile is None:
            return []
        self._persist_columns(dataset, ctx.profile, None, user_id)
        self.db.commit()
        return self.columns.list_for_dataset(dataset_id)

    def get_latest(self, dataset_id: str, user_id: str) -> QualityReportResponse | None:
        """Return the latest persisted quality report for a dataset."""
        self._load_owned_dataset(dataset_id, user_id)
        report = self.reports.latest_for_dataset(dataset_id)
        return self._to_response(report, dataset_id) if report else None

    def get_affected_rows(
        self, dataset_id: int, issue_id: int, user_id: int,
        limit: int = 200, all_columns: bool = False,
    ) -> DatasetPreview:
        """Return the rows of a dataset that triggered a specific quality issue.

        By default only the row number, the identity column and the offending
        column are returned; ``all_columns=True`` returns the full rows.
        """
        dataset = self._load_owned_dataset(dataset_id, user_id)
        issue = self.issues.get(issue_id)
        if issue is None:
            raise NotFoundException("Issue not found.")
        report = self.reports.get(issue.report_id)
        if report is None or report.dataset_id != dataset_id:
            raise NotFoundException("Issue does not belong to this dataset.")

        df = self._read_frame(dataset)
        mask = affected_mask(df, issue.check_key, issue.column_name)
        total = int(mask.sum())
        subset = df[mask].head(limit)

        if all_columns:
            # Full rows, offending column first for quick scanning.
            cols = list(df.columns)
            if issue.column_name in cols:
                cols = [issue.column_name] + [c for c in cols if c != issue.column_name]
        else:
            # Compact view: identity column + the offending column only.
            ident = self._identifier_column(dataset_id, df)
            wanted = [ident, issue.column_name]
            # For duplicate columns, also show the column it duplicates so the
            # match is visible side by side.
            if issue.check_key == "duplicate_columns" and issue.sample:
                wanted.append(issue.sample[0])
            cols = [c for c in dict.fromkeys(wanted) if c and c in df.columns]
            if not cols:
                cols = list(df.columns)[:3]
        row_numbers = [int(i) for i in subset.index]
        subset = subset[cols]

        subset = subset.astype(object).where(pd.notna(subset), None)
        rows = subset.to_dict(orient="records")
        for n, row in zip(row_numbers, rows):
            row["#"] = n
        return DatasetPreview(
            columns=["#", *[str(c) for c in cols]],
            rows=rows,
            total_rows=total,
        )

    # ---- targeted one-click fix ---------------------------------------- #
    def fix_issue(self, dataset_id: int, issue_id: int, user_id: int) -> dict:
        """Apply the targeted fix for one issue, then re-analyze the dataset."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        issue = self.issues.get(issue_id)
        if issue is None:
            raise NotFoundException("Issue not found.")
        report = self.reports.get(issue.report_id)
        if report is None or report.dataset_id != dataset_id:
            raise NotFoundException("Issue does not belong to this dataset.")
        if issue.check_key not in FIXABLE_CHECKS:
            raise BadRequestException("This issue has no automated fix — use one-click cleaning instead.")

        df = self._read_frame(dataset)
        ident = self._identifier_column(dataset_id, df)
        batch = self._create_batch(dataset, len(df), user_id)

        try:
            result = apply_fix(df, issue.check_key, issue.column_name)
        except UnfixableIssueError as exc:
            raise BadRequestException(str(exc)) from exc

        changes = self._diff_changes(df, result.df, issue.column_name, ident)
        fix_row = self.fixes.create(
            batch_id=batch.id, dataset_id=dataset.id,
            check_key=issue.check_key, column_name=issue.column_name,
            identifier_column=ident, severity=issue.severity, problem=issue.problem,
            op=result.op, rows_affected=result.rows_affected,
            detail=result.detail, changes=changes, created_by=user_id,
        )
        self._persist_fixed_frame(dataset, result.df)
        self.history.create(
            user_id=user_id, dataset_id=dataset.id, action="fix",
            summary=f"{result.detail} ({issue.check_key})",
            payload={"op": result.op, "rows_affected": result.rows_affected},
            created_by=user_id,
        )
        self.db.commit()

        # Re-run analysis so the score and remaining issues reflect the fix.
        new_report = self.analyze(dataset_id, user_id)
        return {
            "op": result.op,
            "rows_affected": result.rows_affected,
            "detail": result.detail,
            "fix": FixRecord.model_validate(fix_row),
            "report": new_report,
        }

    def fix_all(self, dataset_id: int, user_id: int) -> dict:
        """Apply every fixable issue's targeted fix as one undoable batch."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        report = self.reports.latest_for_dataset(dataset_id)
        if report is None:
            raise BadRequestException("Run the quality analysis before fixing issues.")

        from app.constants.enums import SEVERITY_ORDER

        issues = [i for i in self.issues.list_for_report(report.id) if i.check_key in FIXABLE_CHECKS]
        issues.sort(key=lambda i: SEVERITY_ORDER.get(i.severity, 9))
        if not issues:
            raise BadRequestException("No automatically fixable issues found.")

        df = self._read_frame(dataset)
        ident = self._identifier_column(dataset_id, df)
        batch = self._create_batch(dataset, len(df), user_id)

        applied: list[IssueFix] = []
        current = df
        seen: set[tuple] = set()
        for issue in issues:
            key = (issue.check_key, issue.column_name)
            if key in seen:
                continue
            seen.add(key)
            try:
                result = apply_fix(current, issue.check_key, issue.column_name)
            except UnfixableIssueError:
                continue
            if result.rows_affected == 0:
                continue  # already resolved by an earlier fix in this batch
            changes = self._diff_changes(current, result.df, issue.column_name, ident)
            applied.append(self.fixes.create(
                batch_id=batch.id, dataset_id=dataset.id,
                check_key=issue.check_key, column_name=issue.column_name,
                identifier_column=ident, severity=issue.severity, problem=issue.problem,
                op=result.op, rows_affected=result.rows_affected,
                detail=result.detail, changes=changes, created_by=user_id,
            ))
            current = result.df

        if not applied:
            self.fix_batches.soft_delete(batch)
            self._safe_unlink(batch.snapshot_path)
            self.db.commit()
            raise BadRequestException("Nothing to fix — every fixable issue is already resolved.")

        self._persist_fixed_frame(dataset, current)
        self.history.create(
            user_id=user_id, dataset_id=dataset.id, action="fix_all",
            summary=f"Applied {len(applied)} fixes in one batch",
            payload={"batch_id": batch.id}, created_by=user_id,
        )
        self.db.commit()

        new_report = self.analyze(dataset_id, user_id)
        return {
            "applied": len(applied),
            "fixes": [FixRecord.model_validate(f) for f in applied],
            "report": new_report,
        }

    def undo_fixes(self, dataset_id: int, user_id: int) -> dict:
        """Restore the snapshot taken before the most recent fix batch."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        batch = self.fix_batches.latest_for_dataset(dataset_id)
        if batch is None:
            raise BadRequestException("No fixes to undo.")
        if not Path(batch.snapshot_path).exists():
            raise BadRequestException("The snapshot for this fix batch no longer exists.")

        shutil.copyfile(batch.snapshot_path, dataset.parquet_path)
        restored = pd.read_parquet(dataset.parquet_path)
        self.datasets.update(
            dataset,
            row_count=int(len(restored)),
            col_count=int(restored.shape[1]),
            memory_bytes=int(restored.memory_usage(deep=True).sum()),
        )
        fixes = self.fixes.list_for_batch(batch.id)
        for f in fixes:
            self.fixes.soft_delete(f)
        self.fix_batches.soft_delete(batch)
        self._safe_unlink(batch.snapshot_path)
        self.history.create(
            user_id=user_id, dataset_id=dataset.id, action="undo_fix",
            summary=f"Undid {len(fixes)} fix(es)", payload={"batch_id": batch.id},
            created_by=user_id,
        )
        self.db.commit()

        new_report = self.analyze(dataset_id, user_id)
        return {"undone_fixes": len(fixes), "report": new_report}

    def list_fixes(self, dataset_id: int, user_id: int) -> dict:
        """Return all recorded fixes (newest first) and whether undo is possible."""
        self._load_owned_dataset(dataset_id, user_id)
        fixes = self.fixes.list_for_dataset(dataset_id)
        return {
            "fixes": [FixRecord.model_validate(f) for f in fixes],
            "undoable": self.fix_batches.latest_for_dataset(dataset_id) is not None,
        }

    # ---- exclusions (ignore a validation) ------------------------------ #
    def _apply_exclusions(self, dataset_id: int, ctx: AgentContext) -> None:
        """Re-score WITHOUT the excluded findings, but keep them in the list.

        The excluded issues stay persisted (so they remain visible, in place,
        marked as ignored) — they just don't contribute to the score.
        """
        excl = self.exclusions.list_for_dataset(dataset_id)
        if not excl or ctx.profile is None or ctx.findings is None:
            return
        keys = {(e.check_key, e.column_name) for e in excl}
        kept = [f for f in ctx.findings if (f.check_key, f.column_name) not in keys]
        if len(kept) != len(ctx.findings):
            # Re-score on the kept findings only; leave ctx.findings untouched.
            ctx.score = Scorer().score(kept, ctx.profile)

    def add_exclusion(self, dataset_id: int, user_id: int, check_key: str, column_name: str | None) -> dict:
        """Exclude a validation, then re-analyze so it drops out of the score."""
        self._load_owned_dataset(dataset_id, user_id)
        if self.exclusions.find(dataset_id, check_key, column_name) is None:
            self.exclusions.create(
                dataset_id=dataset_id, user_id=user_id,
                check_key=check_key, column_name=column_name, created_by=user_id,
            )
            self.history.create(
                user_id=user_id, dataset_id=dataset_id, action="exclude",
                summary=f"Excluded {check_key} on {column_name or 'dataset'}",
                payload={"check_key": check_key, "column": column_name}, created_by=user_id,
            )
            self.db.commit()
        report = self.analyze(dataset_id, user_id)
        return {"exclusions": self._exclusion_items(dataset_id), "report": report}

    def remove_exclusion(self, dataset_id: int, user_id: int, check_key: str, column_name: str | None) -> dict:
        """Re-include a previously excluded validation, then re-analyze."""
        self._load_owned_dataset(dataset_id, user_id)
        existing = self.exclusions.find(dataset_id, check_key, column_name)
        if existing is not None:
            self.exclusions.soft_delete(existing)
            self.db.commit()
        report = self.analyze(dataset_id, user_id)
        return {"exclusions": self._exclusion_items(dataset_id), "report": report}

    def list_exclusions(self, dataset_id: int, user_id: int) -> dict:
        """Return all excluded validations for a dataset."""
        self._load_owned_dataset(dataset_id, user_id)
        return {"exclusions": self._exclusion_items(dataset_id)}

    def _exclusion_items(self, dataset_id: int) -> list:
        from app.schemas.ai import ExclusionItem
        return [ExclusionItem.model_validate(e) for e in self.exclusions.list_for_dataset(dataset_id)]

    # ---- fix helpers ----------------------------------------------------- #
    def _create_batch(self, dataset: Dataset, row_count: int, user_id: int):
        """Create a fix batch and snapshot the current parquet for undo."""
        batch = self.fix_batches.create(
            dataset_id=dataset.id, user_id=user_id,
            snapshot_path="", row_count_before=row_count, created_by=user_id,
        )
        snapshot = Path(dataset.parquet_path).with_name(f"{dataset.id}_fixsnap_{batch.id}.parquet")
        shutil.copyfile(dataset.parquet_path, snapshot)
        self.fix_batches.update(batch, snapshot_path=str(snapshot))
        return batch

    def _persist_fixed_frame(self, dataset: Dataset, df: pd.DataFrame) -> None:
        final = df.reset_index(drop=True)
        final.to_parquet(dataset.parquet_path, index=False)
        self.datasets.update(
            dataset,
            row_count=int(len(final)),
            col_count=int(final.shape[1]),
            memory_bytes=int(final.memory_usage(deep=True).sum()),
        )

    def _identifier_column(self, dataset_id: int, df: pd.DataFrame) -> str | None:
        """Pick the best row-identity column (id type, unique, or *_id name)."""
        cols = self.columns.list_for_dataset(dataset_id)
        for c in cols:
            if c.semantic_type == "id" and c.name in df.columns:
                return c.name
        for c in cols:
            if c.cardinality_ratio >= 0.999 and c.distinct_count > 1 and c.name in df.columns:
                return c.name
        for name in df.columns:
            lname = str(name).lower()
            if lname == "id" or lname.endswith(("_id", "_key", "pin", "pin16")):
                return str(name)
        return None

    def _diff_changes(
        self, before: pd.DataFrame, after: pd.DataFrame,
        column: str | None, ident: str | None,
    ) -> list[dict]:
        """Sample the concrete value changes a fix made (before → after)."""
        def jsonable(v):
            try:
                if v is None or pd.isna(v):
                    return None
            except (TypeError, ValueError):
                pass
            if isinstance(v, (np.integer, np.floating, np.bool_)):
                return v.item()
            return str(v) if not isinstance(v, (int, float, str, bool)) else v

        changes: list[dict] = []

        # Rows removed by the fix (indices are preserved by the fixer).
        removed = before.index.difference(after.index)
        for idx in list(removed)[:_MAX_CHANGES]:
            row = before.loc[idx]
            changes.append({
                "row_index": int(idx),
                "identifier": jsonable(row.get(ident)) if ident else None,
                "old_value": jsonable(row.get(column)) if column else "(row)",
                "new_value": "(row removed)",
            })
        if changes:
            return changes

        # Column dropped entirely.
        if column and column in before.columns and column not in after.columns:
            return [{"row_index": -1, "identifier": None,
                     "old_value": f"column '{column}'", "new_value": "(column removed)"}]

        # Value-level changes within the fixed column.
        if column and column in before.columns and column in after.columns:
            b = before[column].astype(object).where(pd.notna(before[column]), None)
            a = after[column].astype(object).where(pd.notna(after[column]), None)
            a = a.reindex(b.index)
            changed = b.fillna("\x00") != a.fillna("\x00")
            for idx in list(before.index[changed])[:_MAX_CHANGES]:
                changes.append({
                    "row_index": int(idx),
                    "identifier": jsonable(before.loc[idx].get(ident)) if ident else None,
                    "old_value": jsonable(b.loc[idx]),
                    "new_value": jsonable(a.loc[idx]),
                })
        return changes

    def _safe_unlink(self, path: str | None) -> None:
        if not path:
            return
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            self.logger.warning("Could not delete snapshot %s", path)

    def _to_response(self, report, dataset_id: str) -> QualityReportResponse:
        issues = self.issues.list_for_report(report.id)
        dataset = self.db.get(Dataset, dataset_id)
        total_rows = dataset.row_count if dataset else 0
        response = QualityReportResponse.model_validate(report)
        response.dataset_id = dataset_id
        excluded_keys = {
            (e.check_key, e.column_name) for e in self.exclusions.list_for_dataset(dataset_id)
        }
        issue_responses = []
        for i in issues:
            r = QualityIssueResponse.model_validate(i)
            r.column_level = i.check_key in COLUMN_LEVEL_CHECKS
            r.excluded = (i.check_key, i.column_name) in excluded_keys
            # An excluded validation can't also be "fixed" — hide the fix action.
            r.fixable = (not r.excluded) and self._is_fixable(i.check_key, i.count, total_rows)
            r.suggest_drop = (
                not r.excluded
                and i.check_key in {"missing_values", "blank_strings"}
                and bool(total_rows) and i.count >= total_rows
            )
            issue_responses.append(r)
        response.issues = issue_responses
        previous = self.db.scalars(
            select(QualityReport)
            .where(QualityReport.dataset_id == dataset_id, QualityReport.id < report.id)
            .order_by(QualityReport.id.desc())
        ).first()
        response.previous_score = previous.overall_score if previous else None
        return response
