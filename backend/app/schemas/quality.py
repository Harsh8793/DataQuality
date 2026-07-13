"""Quality report and cleaning schemas."""

from __future__ import annotations

from pydantic import BaseModel

# Column-level checks describe the whole column, not individual rows — so their
# "N affected" count means columns/relationships, not rows.
COLUMN_LEVEL_CHECKS = {
    "constant_column", "duplicate_columns", "high_cardinality",
    "low_cardinality", "datatype_mismatch",
}


class QualityIssueResponse(BaseModel):
    """A single quality issue with optional AI explanation."""

    id: int
    check_key: str
    dimension: str
    severity: str
    count: int
    column_name: str | None = None
    sample: list = []
    problem: str | None = None
    why: str | None = None
    business_impact: str | None = None
    recommended_fix: str | None = None
    confidence: float | None = None
    # Set by the service (needs the dataset row count); default off.
    fixable: bool = False
    column_level: bool = False
    suggest_drop: bool = False  # column is 100% empty — dropping is recommended
    excluded: bool = False  # user ignored this validation (kept in list, not scored)

    model_config = {"from_attributes": True}


class QualityReportResponse(BaseModel):
    """Full quality report: scores plus issues."""

    id: int
    dataset_id: int
    overall_score: float
    previous_score: float | None = None
    completeness: float
    accuracy: float
    consistency: float
    uniqueness: float
    validity: float
    integrity: float
    duplicate_rows: int
    total_issues: int
    issues: list[QualityIssueResponse] = []

    model_config = {"from_attributes": True}


class CleaningOpResponse(BaseModel):
    """A single applied cleaning operation."""

    op: str
    column: str | None = None
    rows_affected: int
    detail: str = ""
    rows: list[int] = []


class CompareMetrics(BaseModel):
    """A before/after metric pair."""

    label: str
    before: float
    after: float


class CleaningResultResponse(BaseModel):
    """Result of a cleaning run, including the new dataset id and comparison."""

    cleaned_dataset_id: int
    operations: list[CleaningOpResponse]
    comparison: list[CompareMetrics]
