"""Generated report and dashboard history models."""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import AuditMixin, Base


class GeneratedReport(AuditMixin, Base):
    """A materialized export artifact (PDF/Excel/JSON/CSV)."""

    __tablename__ = "generated_reports"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    dataset_id: Mapped[int] = mapped_column(Integer, ForeignKey("datasets.id"), index=True)
    report_type: Mapped[str] = mapped_column(String(16))  # pdf | xlsx | json | csv
    title: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)


class DashboardHistory(AuditMixin, Base):
    """A cached auto-generated dashboard specification for a dataset."""

    __tablename__ = "dashboard_history"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    dataset_id: Mapped[int] = mapped_column(Integer, ForeignKey("datasets.id"), index=True)
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
