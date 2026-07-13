"""Governance classification model."""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import AuditMixin, Base


class GovernanceReport(AuditMixin, Base):
    """Dataset-level governance classification and ingestion recommendation."""

    __tablename__ = "governance_reports"

    dataset_id: Mapped[int] = mapped_column(Integer, ForeignKey("datasets.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)

    classification: Mapped[str] = mapped_column(String(32), default="internal")
    pii_columns: Mapped[list] = mapped_column(JSON, default=list)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    ingestion_tier: Mapped[str] = mapped_column(String(16), default="bronze")
    tier_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
