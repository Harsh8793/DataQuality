"""Scoring engine: convert findings into a 0-100 six-dimension quality score."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.constants.enums import SEVERITY_WEIGHT, Dimension, Severity
from app.core.engines.profiler import DatasetProfile
from app.core.engines.quality_checks import QualityFinding

# Relative weight of each dimension in the overall score.
_DIMENSION_WEIGHTS: dict[str, float] = {
    Dimension.COMPLETENESS: 0.25,
    Dimension.VALIDITY: 0.20,
    Dimension.UNIQUENESS: 0.15,
    Dimension.CONSISTENCY: 0.15,
    Dimension.ACCURACY: 0.15,
    Dimension.INTEGRITY: 0.10,
}


@dataclass
class QualityScore:
    """Computed quality score with per-dimension breakdown."""

    overall: float
    dimensions: dict[str, float] = field(default_factory=dict)
    duplicate_rows: int = 0
    total_issues: int = 0


class Scorer:
    """Computes a weighted quality score from findings.

    Each dimension starts at 100 and accrues penalties scaled by severity and
    the fraction of cells/rows affected, then dimensions are combined into an
    overall score using :data:`_DIMENSION_WEIGHTS`.
    """

    def score(self, findings: list[QualityFinding], profile: DatasetProfile) -> QualityScore:
        """Return a :class:`QualityScore` for the given findings.

        Each dimension starts at 100 and each finding subtracts a penalty equal
        to its severity weight scaled by the fraction of *rows* it affects
        (with a floor so even a small-but-real issue counts).
        """
        total_rows = max(profile.row_count, 1)
        dim_scores = {dim: 100.0 for dim in _DIMENSION_WEIGHTS}
        duplicate_rows = 0

        for f in findings:
            weight = SEVERITY_WEIGHT.get(f.severity, 1.0)
            # Fraction of rows affected drives severity of the penalty.
            fraction = min(f.count / total_rows, 1.0)
            penalty = weight * (0.6 + 0.4 * fraction)
            dim_scores[f.dimension] = max(dim_scores.get(f.dimension, 100.0) - penalty, 0.0)
            if f.check_key == "duplicate_rows":
                duplicate_rows = f.count

        overall = sum(dim_scores[d] * w for d, w in _DIMENSION_WEIGHTS.items())
        return QualityScore(
            overall=round(overall, 1),
            dimensions={d: round(v, 1) for d, v in dim_scores.items()},
            duplicate_rows=duplicate_rows,
            total_issues=len(findings),
        )
