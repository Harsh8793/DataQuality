"""Scoring engine: the share of rows that pass every quality check.

The score is deliberately one idea: **a row is clean if nothing flags it, and
the score is the percentage of clean rows.** A row failing three checks counts
once, so no fix ever gets credit twice and the number always reads as "this
much of your data is usable as-is".

The same measurement, restricted to one dimension's checks, gives that
dimension's score. The overall score is *not* an average of the six — it is the
same measurement over every check, which is why it is always less than or equal
to each dimension score.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.constants.enums import COLUMN_LEVEL_CHECKS, Dimension
from app.core.engines.affected import affected_mask
from app.core.engines.profiler import DatasetProfile
from app.core.engines.quality_checks import QualityFinding

_DIMENSIONS: tuple[str, ...] = (
    Dimension.COMPLETENESS,
    Dimension.ACCURACY,
    Dimension.CONSISTENCY,
    Dimension.UNIQUENESS,
    Dimension.VALIDITY,
    Dimension.INTEGRITY,
)


@dataclass
class QualityScore:
    """Computed quality score with per-dimension breakdown."""

    overall: float
    dimensions: dict[str, float] = field(default_factory=dict)
    duplicate_rows: int = 0
    total_issues: int = 0
    dirty_rows: int = 0
    clean_rows: int = 0


class Scorer:
    """Computes ``100 * clean_rows / total_rows`` overall and per dimension."""

    def score(
        self,
        findings: list[QualityFinding],
        profile: DatasetProfile,
        df: pd.DataFrame,
    ) -> QualityScore:
        """Return a :class:`QualityScore` for the given findings.

        ``df`` is required: the score is defined in terms of which *rows* each
        finding touches, and that can only be resolved against the frame.
        """
        total_rows = profile.row_count
        duplicate_rows = next(
            (f.count for f in findings if f.check_key == "duplicate_rows"), 0
        )

        # An empty dataset has no clean rows to speak of — scoring it 100
        # because "nothing failed" would be exactly backwards.
        if total_rows == 0 or df.empty:
            return QualityScore(
                overall=0.0,
                dimensions=dict.fromkeys(_DIMENSIONS, 0.0),
                duplicate_rows=duplicate_rows,
                total_issues=len(findings),
            )

        dirty_all = pd.Series(False, index=df.index)
        dirty_by_dim = {d: pd.Series(False, index=df.index) for d in _DIMENSIONS}

        for f in findings:
            # Column-level checks describe the shape of a column, not the
            # contents of any particular row. ``affected_mask`` returns every
            # non-null row for them, which would dirty the whole dataset over a
            # single constant column, so they are listed but never scored.
            if f.check_key in COLUMN_LEVEL_CHECKS:
                continue
            mask = self._mask(df, f)
            if mask is None:
                continue
            dirty_all |= mask
            if f.dimension in dirty_by_dim:
                dirty_by_dim[f.dimension] |= mask

        dirty = int(dirty_all.sum())
        return QualityScore(
            overall=self._pct(dirty, total_rows),
            dimensions={
                d: self._pct(int(m.sum()), total_rows) for d, m in dirty_by_dim.items()
            },
            duplicate_rows=duplicate_rows,
            total_issues=len(findings),
            dirty_rows=dirty,
            clean_rows=max(total_rows - dirty, 0),
        )

    @staticmethod
    def _pct(dirty: int, total: int) -> float:
        """Percentage of rows left clean, rounded to one decimal."""
        return round(100.0 * (1.0 - min(dirty / total, 1.0)), 1)

    @staticmethod
    def _mask(df: pd.DataFrame, f: QualityFinding) -> pd.Series | None:
        """Resolve the rows a finding touches, or ``None`` if it touches none."""
        if f.row_index:
            # Custom rules carry positional offsets (DuckDB reset the index).
            positions = [i for i in f.row_index if 0 <= i < len(df)]
            if not positions:
                return None
            mask = pd.Series(False, index=df.index)
            mask.iloc[positions] = True
            return mask
        try:
            return affected_mask(df, f.check_key, f.column_name)
        except Exception:  # noqa: BLE001 - a mask that won't build must not break scoring
            return None
