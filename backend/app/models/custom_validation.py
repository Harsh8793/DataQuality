"""User-defined (AI-assisted) custom quality validations."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import AuditMixin, Base


class CustomValidation(AuditMixin, Base):
    """A custom quality check defined by the user (via the AI validation builder).

    ``condition`` is a DuckDB boolean WHERE expression selecting the *problem*
    rows (the ones that violate the rule). It runs during analysis and produces
    a normal quality issue (``check_key = "custom_<id>"``).
    """

    __tablename__ = "custom_validations"

    dataset_id: Mapped[int] = mapped_column(Integer, ForeignKey("datasets.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    dimension: Mapped[str] = mapped_column(String(32), default="validity")
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    condition: Mapped[str] = mapped_column(Text)  # DuckDB WHERE expression
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
