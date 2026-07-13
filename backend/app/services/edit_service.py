"""Manual data editing: apply cell edits, keep an undo history, re-analyze."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.exceptions.base import BadRequestException
from app.repositories.analysis_repository import AnalysisHistoryRepository
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.edit_repository import EditRepository
from app.schemas.ai import (
    ApplyEditsResponse,
    CellEdit,
    EditBatchItem,
    EditHistoryResponse,
    UndoEditResponse,
)
from app.schemas.dataset import RowQueryResponse
from app.services.analysis_service import AnalysisService
from app.services.base import BaseService, DatasetContextMixin


def _jsonable(value):
    """Convert a pandas/numpy cell value to a JSON-safe python value."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return str(value)
    return value


class EditService(BaseService, DatasetContextMixin):
    """Applies user cell edits with full undo history and re-analysis."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.datasets = DatasetRepository(db)
        self.edits = EditRepository(db)
        self.history = AnalysisHistoryRepository(db)

    # ---- apply ---------------------------------------------------------- #
    def apply(self, dataset_id: int, user_id: int, edits: list[CellEdit]) -> ApplyEditsResponse:
        """Apply a batch of cell edits, persist it as one undoable unit, re-analyze."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        df = self._read_frame(dataset)

        records: list[dict] = []
        for edit in edits:
            if edit.column not in df.columns:
                raise BadRequestException(f"Column '{edit.column}' does not exist.")
            if edit.row_index >= len(df):
                raise BadRequestException(f"Row {edit.row_index} is out of range (0-{len(df) - 1}).")
            old = _jsonable(df.at[edit.row_index, edit.column])
            df = self._assign(df, edit.row_index, edit.column, edit.value)
            records.append({
                "row_index": edit.row_index, "column": edit.column,
                "old_value": old, "new_value": _jsonable(df.at[edit.row_index, edit.column]),
            })

        df.to_parquet(dataset.parquet_path, index=False)
        self.datasets.update(dataset, memory_bytes=int(df.memory_usage(deep=True).sum()))
        batch = self.edits.create(
            dataset_id=dataset.id, user_id=user_id, edits=records,
            row_count=int(len(df)), created_by=user_id,
        )
        self.history.create(
            user_id=user_id, dataset_id=dataset.id, action="edit",
            summary=f"Edited {len(records)} cell(s)",
            payload={"edit_id": batch.id}, created_by=user_id,
        )
        self.db.commit()

        report = AnalysisService(self.db).analyze(dataset_id, user_id)
        return ApplyEditsResponse(edit_id=batch.id, applied=len(records), report=report)

    # ---- undo ------------------------------------------------------------ #
    def undo_last(self, dataset_id: int, user_id: int) -> UndoEditResponse:
        """Revert the most recent edit batch, then re-analyze."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        batch = self.edits.latest_for_dataset(dataset_id)
        if batch is None:
            raise BadRequestException("Nothing to undo — no manual edits recorded.")

        df = self._read_frame(dataset)
        if len(df) != batch.row_count:
            raise BadRequestException(
                "The data shape has changed since this edit (rows were added or removed "
                "by cleaning or a fix), so this edit can no longer be undone safely."
            )

        for record in reversed(batch.edits):
            column, row = record["column"], record["row_index"]
            if column not in df.columns or row >= len(df):
                raise BadRequestException(
                    f"Column '{column}' or row {row} no longer exists — undo is not possible."
                )
            df = self._assign(df, row, column, record["old_value"])

        df.to_parquet(dataset.parquet_path, index=False)
        self.datasets.update(dataset, memory_bytes=int(df.memory_usage(deep=True).sum()))
        self.edits.soft_delete(batch)
        self.history.create(
            user_id=user_id, dataset_id=dataset.id, action="undo_edit",
            summary=f"Undid {len(batch.edits)} cell edit(s)",
            payload={"edit_id": batch.id}, created_by=user_id,
        )
        self.db.commit()

        report = AnalysisService(self.db).analyze(dataset_id, user_id)
        remaining = self.edits.count(dataset_id=dataset_id)
        return UndoEditResponse(undone=len(batch.edits), remaining=remaining, report=report)

    # ---- filtered row query (for the editor) --------------------------- #
    def query_rows(
        self, dataset_id: int, user_id: int, *,
        filter_column: str | None, filter_op: str | None, filter_value: str | None,
        limit: int, offset: int,
    ) -> RowQueryResponse:
        """Return a paginated (optionally filtered) slice with true row indices."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        df = self._read_frame(dataset)
        total = int(len(df))

        mask = self._filter_mask(df, filter_column, filter_op, filter_value)
        subset = df[mask] if mask is not None else df
        matched = int(len(subset))

        page = subset.iloc[offset : offset + limit]
        # df was written with a clean RangeIndex, so page.index == absolute row positions.
        row_indices = [int(i) for i in page.index]
        page = page.astype(object).where(pd.notna(page), None)
        return RowQueryResponse(
            columns=[str(c) for c in df.columns],
            rows=page.to_dict(orient="records"),
            row_indices=row_indices,
            total_rows=total,
            matched_rows=matched,
        )

    @staticmethod
    def _filter_mask(df: pd.DataFrame, column: str | None, op: str | None, value):
        """Build a boolean mask for one filter, or None if no valid filter."""
        if not column or not op or column not in df.columns:
            return None
        s = df[column]
        text = s.astype(str)

        if op == "empty":
            return s.isna() | (text.str.strip() == "")
        if op == "not_empty":
            return s.notna() & (text.str.strip() != "")

        val = "" if value is None else str(value)
        if op == "contains":
            return s.notna() & text.str.contains(val, case=False, na=False, regex=False)
        if op in {"eq", "neq"}:
            eq = text.str.strip().str.lower() == val.strip().lower()
            return eq if op == "eq" else ~eq
        if op in {"gt", "gte", "lt", "lte"}:
            num = pd.to_numeric(s, errors="coerce")
            try:
                target = float(val)
            except (TypeError, ValueError):
                # Non-numeric target → compare as dates, else no match.
                left = pd.to_datetime(s, errors="coerce")
                right = pd.to_datetime(val, errors="coerce")
                if pd.isna(right):
                    return pd.Series([False] * len(df), index=df.index)
                cmp = {"gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right}
                return cmp[op].fillna(False)
            cmp = {"gt": num > target, "gte": num >= target, "lt": num < target, "lte": num <= target}
            return cmp[op].fillna(False)
        return None

    # ---- history ----------------------------------------------------------- #
    def get_history(self, dataset_id: int, user_id: int) -> EditHistoryResponse:
        """Return recent (still undoable) edit batches, newest first."""
        self._load_owned_dataset(dataset_id, user_id)
        batches = self.edits.list_for_dataset(dataset_id)
        return EditHistoryResponse(
            items=[EditBatchItem(id=b.id, edits=b.edits, created_at=b.created_at) for b in batches]
        )

    # ---- helpers ------------------------------------------------------------ #
    @staticmethod
    def _assign(df: pd.DataFrame, row: int, column: str, value) -> pd.DataFrame:
        """Assign one cell, coercing the value to the column's type safely."""
        series = df[column]
        empty = value is None or (isinstance(value, str) and value.strip() == "")

        if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
            if empty:
                coerced = np.nan
            else:
                try:
                    coerced = float(value)
                except (TypeError, ValueError):
                    raise BadRequestException(
                        f"'{value}' is not a valid number for column '{column}'."
                    ) from None
            # Int columns can't hold NaN or fractions — widen to float first.
            if pd.api.types.is_integer_dtype(series) and (
                pd.isna(coerced) or not float(coerced).is_integer()
            ):
                df[column] = series.astype("float64")
            elif pd.api.types.is_integer_dtype(series):
                coerced = int(coerced)
            df.loc[row, column] = coerced
            return df

        if pd.api.types.is_bool_dtype(series):
            if empty:
                df[column] = series.astype(object)
                df.loc[row, column] = None
                return df
            truthy = str(value).strip().lower() in {"true", "1", "yes", "y"}
            df.loc[row, column] = truthy
            return df

        # Object/text columns accept anything (empty string clears to null).
        df.loc[row, column] = None if empty else str(value)
        return df
