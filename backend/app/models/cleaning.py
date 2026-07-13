"""Cleaning report model: persists a cleaning run's ops and before/after."""

from __future__ import annotations

from sqlalchemy import JSON, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import AuditMixin, Base


class CleaningReport(AuditMixin, Base):
    """Result of a one-click cleaning run (survives navigation and reloads)."""

    __tablename__ = "cleaning_reports"

    dataset_id: Mapped[int] = mapped_column(Integer, ForeignKey("datasets.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    cleaned_dataset_id: Mapped[int] = mapped_column(Integer, ForeignKey("datasets.id"))

    operations: Mapped[list] = mapped_column(JSON, default=list)
    comparison: Mapped[list] = mapped_column(JSON, default=list)
    before_score: Mapped[float] = mapped_column(Float, default=0.0)
    after_score: Mapped[float] = mapped_column(Float, default=0.0)
