"""Issue-fix audit models: what was repaired, with before/after values."""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import AuditMixin, Base


class FixBatch(AuditMixin, Base):
    """One undoable unit of applied fixes (a single fix, or fix-all).

    ``snapshot_path`` points to a parquet copy taken before the batch was
    applied — undo restores it wholesale.
    """

    __tablename__ = "fix_batches"

    dataset_id: Mapped[int] = mapped_column(Integer, ForeignKey("datasets.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    snapshot_path: Mapped[str] = mapped_column(String(512))
    row_count_before: Mapped[int] = mapped_column(Integer, default=0)


class IssueFix(AuditMixin, Base):
    """A single applied fix with a sample of the concrete value changes."""

    __tablename__ = "issue_fixes"

    batch_id: Mapped[int] = mapped_column(Integer, ForeignKey("fix_batches.id"), index=True)
    dataset_id: Mapped[int] = mapped_column(Integer, ForeignKey("datasets.id"), index=True)
    check_key: Mapped[str] = mapped_column(String(64))
    column_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Row-identity column used to label the change rows (e.g. TAXPIN16).
    identifier_column: Mapped[str | None] = mapped_column(String(255), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    problem: Mapped[str | None] = mapped_column(String(255), nullable=True)
    op: Mapped[str] = mapped_column(String(64))
    rows_affected: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(String(512), default="")
    # Sample of concrete changes: [{row_index, identifier, old_value, new_value}]
    changes: Mapped[list] = mapped_column(JSON, default=list)
