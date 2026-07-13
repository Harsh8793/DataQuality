"""Issue-exclusion model: validations a user has chosen to ignore per dataset."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import AuditMixin, Base


class IssueExclusion(AuditMixin, Base):
    """A (check_key, column) the user excluded from quality analysis.

    Excluded findings are dropped before scoring, so they no longer appear as
    issues nor lower the quality score. Excluding is reversible (re-include).
    """

    __tablename__ = "issue_exclusions"

    dataset_id: Mapped[int] = mapped_column(Integer, ForeignKey("datasets.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    check_key: Mapped[str] = mapped_column(String(64))
    column_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
