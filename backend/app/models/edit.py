"""Manual data-edit models (cell edits with undo history)."""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import AuditMixin, Base


class DatasetEdit(AuditMixin, Base):
    """One saved batch of manual cell edits (the undo unit).

    ``edits`` is a list of ``{row_index, column, old_value, new_value}`` so the
    batch can be reverted exactly. ``row_count`` snapshots the frame length at
    edit time — undo is refused if rows were added/removed since.
    """

    __tablename__ = "dataset_edits"

    dataset_id: Mapped[int] = mapped_column(Integer, ForeignKey("datasets.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    edits: Mapped[list] = mapped_column(JSON, default=list)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
