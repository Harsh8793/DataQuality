"""Schemas for the AI playground features: explain, story, command, compare."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.chat import ChartSpec, KpiCard
from app.schemas.quality import QualityReportResponse


# ---- "Explain this" ----------------------------------------------------- #
class ExplainRequest(BaseModel):
    """A widget the user wants explained in plain business terms."""

    kind: str = Field(pattern="^(kpi|chart)$")
    label: str = Field(min_length=1, max_length=200)
    value: float | int | None = None
    format: str | None = None
    chart_type: str | None = None
    x: str | None = None
    y: str | None = None
    # A small sample of the chart's points; capped to keep prompts tiny.
    data: list[dict] = Field(default_factory=list, max_length=15)


class ExplainResponse(BaseModel):
    """Plain-language explanation of a widget."""

    explanation: str
    generated_by: str  # "ai" | "fallback"


# ---- Data story ---------------------------------------------------------- #
class StoryResponse(BaseModel):
    """AI executive summary of a dataset."""

    story: str
    generated_by: str


# ---- Chart-on-command ----------------------------------------------------- #
class ChartCommandRequest(BaseModel):
    """A natural-language request to create a dashboard widget."""

    command: str = Field(min_length=1, max_length=300)


class ChartCommandResponse(BaseModel):
    """The widget built from an NL command (exactly one of kpi/chart set)."""

    kind: str  # "kpi" | "chart"
    kpi: KpiCard | None = None
    chart: ChartSpec | None = None
    message: str


# ---- Dataset comparison ---------------------------------------------------- #
class CompareRequest(BaseModel):
    """Compare two datasets the user owns."""

    left_id: int
    right_id: int


class ColumnShift(BaseModel):
    """Numeric/null drift for a column present in both datasets."""

    column: str
    left_mean: float | None = None
    right_mean: float | None = None
    mean_change_pct: float | None = None
    left_null_pct: float
    right_null_pct: float


class CompareResponse(BaseModel):
    """Schema diff + distribution shifts between two datasets, AI-narrated."""

    left_name: str
    right_name: str
    left_rows: int
    right_rows: int
    left_cols: int
    right_cols: int
    added_columns: list[str]
    removed_columns: list[str]
    common_columns: int
    column_shifts: list[ColumnShift]
    narrative: str
    generated_by: str


# ---- Targeted issue fix ------------------------------------------------------ #
class FixChange(BaseModel):
    """One concrete value change made by a fix."""

    row_index: int
    identifier: str | None = None
    old_value: Any = None
    new_value: Any = None


class FixRecord(BaseModel):
    """An applied fix with its audit trail."""

    id: int
    batch_id: int
    check_key: str
    column_name: str | None = None
    identifier_column: str | None = None
    severity: str = "medium"
    problem: str | None = None
    op: str
    rows_affected: int
    detail: str = ""
    changes: list[FixChange] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class IssueFixResponse(BaseModel):
    """Result of applying a one-click fix for a single quality issue."""

    op: str
    rows_affected: int
    detail: str
    fix: FixRecord | None = None
    report: QualityReportResponse


class FixAllResponse(BaseModel):
    """Result of fixing every fixable issue in one batch."""

    applied: int
    fixes: list[FixRecord]
    report: QualityReportResponse


class FixListResponse(BaseModel):
    """All recorded fixes for a dataset, newest first."""

    fixes: list[FixRecord]
    undoable: bool


class UndoFixResponse(BaseModel):
    """Result of undoing the most recent fix batch."""

    undone_fixes: int
    report: QualityReportResponse


# ---- Manual data editing ----------------------------------------------------- #
class CellEdit(BaseModel):
    """One cell change: row position (0-based, full-frame) + column + new value."""

    row_index: int = Field(ge=0)
    column: str = Field(min_length=1, max_length=255)
    value: Any = None


class ApplyEditsRequest(BaseModel):
    """A batch of manual cell edits to save as one undoable unit."""

    edits: list[CellEdit] = Field(min_length=1, max_length=100)


class ApplyEditsResponse(BaseModel):
    """Result of saving edits: the batch id and the fresh quality report."""

    edit_id: int
    applied: int
    report: QualityReportResponse


class UndoEditResponse(BaseModel):
    """Result of undoing the most recent edit batch."""

    undone: int
    remaining: int
    report: QualityReportResponse


class EditBatchItem(BaseModel):
    """One saved edit batch shown in the history list."""

    id: int
    edits: list[dict]
    created_at: datetime


class EditHistoryResponse(BaseModel):
    """Recent edit batches for a dataset, newest first."""

    items: list[EditBatchItem]


# ---- Issue exclusions (ignore a validation) --------------------------------- #
class ExclusionRequest(BaseModel):
    """Exclude or re-include a validation from quality analysis."""

    check_key: str = Field(min_length=1, max_length=64)
    column_name: str | None = None


class ExclusionItem(BaseModel):
    """A validation the user has excluded."""

    id: int
    check_key: str
    column_name: str | None = None

    model_config = {"from_attributes": True}


class ExclusionActionResponse(BaseModel):
    """Result of excluding/including a validation: fresh report + the list."""

    exclusions: list[ExclusionItem]
    report: QualityReportResponse


class ExclusionListResponse(BaseModel):
    """All excluded validations for a dataset."""

    exclusions: list[ExclusionItem]


# ---- Starter questions ------------------------------------------------------ #
class SuggestionsResponse(BaseModel):
    """Clickable starter questions generated from the dataset's own columns."""

    questions: list[str]
