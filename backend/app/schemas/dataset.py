"""Dataset, column and preview schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DatasetSummary(BaseModel):
    """High-level dataset metadata shown after upload."""

    id: int
    name: str
    file_format: str
    encoding: str | None = None
    delimiter: str | None = None
    row_count: int
    col_count: int
    file_size_bytes: int
    memory_bytes: int
    status: str
    is_cleaned: bool
    parent_id: int | None = None
    approval_status: str = "not_required"
    approval_note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalRequest(BaseModel):
    """Approve or reject a dataset pending review."""

    approved: bool
    note: str | None = None


class ColumnProfileResponse(BaseModel):
    """Serialized column profile."""

    name: str
    ordinal: int
    physical_type: str
    semantic_type: str
    null_count: int
    null_pct: float
    distinct_count: int
    cardinality_ratio: float
    min_val: str | None = None
    max_val: str | None = None
    mean_val: float | None = None
    std_val: float | None = None
    sample_values: list = []
    business_name: str | None = None
    description: str | None = None
    sensitivity: str | None = None
    is_pii: bool = False

    model_config = {"from_attributes": True}


class DatasetPreview(BaseModel):
    """A small preview slice of dataset rows."""

    columns: list[str]
    rows: list[dict]
    total_rows: int


class RowQueryRequest(BaseModel):
    """A filtered, paginated row query for the editor (single optional filter)."""

    filter_column: str | None = None
    filter_op: str | None = None  # eq|neq|contains|gt|gte|lt|lte|empty|not_empty
    filter_value: str | None = None
    limit: int = 100
    offset: int = 0


class RowQueryResponse(BaseModel):
    """Rows matching a query, each paired with its true dataset row index."""

    columns: list[str]
    rows: list[dict]
    row_indices: list[int]  # absolute 0-based index of each returned row
    total_rows: int         # rows in the whole dataset
    matched_rows: int       # rows matching the filter
