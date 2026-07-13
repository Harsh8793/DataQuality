"""Dataset, uploaded file and column profile models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import AuditMixin, Base


class UploadedFile(AuditMixin, Base):
    """Raw uploaded file metadata (provenance record)."""

    __tablename__ = "uploaded_files"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))
    extension: Mapped[str] = mapped_column(String(16))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[str] = mapped_column(String(512))


class Dataset(AuditMixin, Base):
    """A tabular dataset materialized as parquet, with summary metadata."""

    __tablename__ = "datasets"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    uploaded_file_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("uploaded_files.id"), nullable=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("datasets.id"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255))
    file_format: Mapped[str] = mapped_column(String(16))
    encoding: Mapped[str | None] = mapped_column(String(32), nullable=True)
    delimiter: Mapped[str | None] = mapped_column(String(8), nullable=True)

    row_count: Mapped[int] = mapped_column(Integer, default=0)
    col_count: Mapped[int] = mapped_column(Integer, default=0)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    memory_bytes: Mapped[int] = mapped_column(Integer, default=0)

    parquet_path: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    is_cleaned: Mapped[bool] = mapped_column(default=False)

    # AI-generated executive summary (cached so it costs tokens only once).
    story: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Human approval gate (set after analysis based on the quality score).
    approval_status: Mapped[str] = mapped_column(String(16), default="not_required", index=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    columns: Mapped[list["DatasetColumn"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )


class DatasetColumn(AuditMixin, Base):
    """Per-column profile: physical + semantic type, stats and metadata."""

    __tablename__ = "dataset_columns"

    dataset_id: Mapped[int] = mapped_column(Integer, ForeignKey("datasets.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    ordinal: Mapped[int] = mapped_column(Integer, default=0)

    physical_type: Mapped[str] = mapped_column(String(32))
    semantic_type: Mapped[str] = mapped_column(String(32), default="text")

    null_count: Mapped[int] = mapped_column(Integer, default=0)
    null_pct: Mapped[float] = mapped_column(Float, default=0.0)
    distinct_count: Mapped[int] = mapped_column(Integer, default=0)
    cardinality_ratio: Mapped[float] = mapped_column(Float, default=0.0)

    min_val: Mapped[str | None] = mapped_column(String(255), nullable=True)
    max_val: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mean_val: Mapped[float | None] = mapped_column(Float, nullable=True)
    std_val: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_values: Mapped[list] = mapped_column(JSON, default=list)

    # Governance / business metadata (filled by GovernanceAgent).
    business_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sensitivity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_pii: Mapped[bool] = mapped_column(default=False)
    owner: Mapped[str | None] = mapped_column(String(120), nullable=True)

    dataset: Mapped["Dataset"] = relationship(back_populates="columns")
