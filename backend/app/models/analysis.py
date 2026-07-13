"""Quality report, quality issue and analysis history models."""

from __future__ import annotations

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import AuditMixin, Base


class QualityReport(AuditMixin, Base):
    """Result of a full quality analysis run for a dataset."""

    __tablename__ = "quality_reports"

    dataset_id: Mapped[int] = mapped_column(Integer, ForeignKey("datasets.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)

    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    completeness: Mapped[float] = mapped_column(Float, default=0.0)
    accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    consistency: Mapped[float] = mapped_column(Float, default=0.0)
    uniqueness: Mapped[float] = mapped_column(Float, default=0.0)
    validity: Mapped[float] = mapped_column(Float, default=0.0)
    integrity: Mapped[float] = mapped_column(Float, default=0.0)

    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0)
    total_issues: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    issues: Mapped[list["QualityIssue"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class QualityIssue(AuditMixin, Base):
    """A single quality issue found during analysis, with AI explanation."""

    __tablename__ = "quality_issues"

    report_id: Mapped[int] = mapped_column(Integer, ForeignKey("quality_reports.id"), index=True)
    column_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    check_key: Mapped[str] = mapped_column(String(64), index=True)
    dimension: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16), index=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    sample: Mapped[list] = mapped_column(JSON, default=list)

    # AI explanation (filled by InsightAgent).
    problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    why: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    report: Mapped["QualityReport"] = relationship(back_populates="issues")


class AnalysisHistory(AuditMixin, Base):
    """Timeline record of analysis actions for auditing and the History view."""

    __tablename__ = "analysis_history"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    dataset_id: Mapped[int] = mapped_column(Integer, ForeignKey("datasets.id"), index=True)
    action: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
