"""Unit tests for the deterministic analytics engines."""

from __future__ import annotations

import pandas as pd

from app.core.engines.cleaner import Cleaner
from app.core.engines.duckdb_engine import DuckDBEngine
from app.core.engines.profiler import Profiler
from app.core.engines.quality_checks import QualityEngine
from app.core.engines.scorer import Scorer
from app.exceptions.base import BadRequestException


def _messy_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "email": ["a@x.com", "bad@@", "c@y.com", None],
            "amount": [10, 20, 30, 1000],
            "country": ["USA", "usa", "United States", "US"],
        }
    )


def test_profiler_detects_email_semantic_type() -> None:
    profile = Profiler().profile(_messy_df())
    email_col = next(c for c in profile.columns if c.name == "email")
    assert email_col.semantic_type == "email"


def test_quality_engine_flags_invalid_email() -> None:
    df = _messy_df()
    profile = Profiler().profile(df)
    findings = QualityEngine().run(df, profile)
    keys = {f.check_key for f in findings}
    assert "invalid_email" in keys
    assert "missing_values" in keys


def test_cleaning_improves_score() -> None:
    df = _messy_df()
    profile = Profiler().profile(df)
    scorer, quality = Scorer(), QualityEngine()
    before = scorer.score(quality.run(df, profile), profile).overall

    cleaned = Cleaner().clean(df, profile).df
    after_profile = Profiler().profile(cleaned)
    after = scorer.score(quality.run(cleaned, after_profile), after_profile).overall
    assert after >= before


def test_duckdb_rejects_non_select() -> None:
    engine = DuckDBEngine()
    try:
        engine.validate("DROP TABLE dataset")
    except BadRequestException:
        return
    raise AssertionError("Expected BadRequestException for non-SELECT SQL")


def test_duckdb_executes_select() -> None:
    df = _messy_df()
    result = DuckDBEngine().execute(df, "SELECT country, COUNT(*) AS n FROM dataset GROUP BY country")
    assert result.row_count > 0
    assert "country" in result.columns
