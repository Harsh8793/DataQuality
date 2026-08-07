"""Quality tab: detection, scoring, explanations and one-click fixes.

Covers ``core/engines/quality_checks.py``, ``scorer.py``, ``explanations.py``
and ``fixer.py`` — the deterministic core the tab renders.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.constants.enums import Dimension, Severity
from app.core.engines.explanations import explain_issue
from app.core.engines.fixer import FIXABLE_CHECKS, UnfixableIssueError, apply_fix
from app.core.engines.profiler import Profiler
from app.core.engines.quality_checks import QualityEngine
from app.core.engines.scorer import Scorer


def run_checks(frame: pd.DataFrame):
    """Profile then run every quality check, as the pipeline does."""
    profile = Profiler().profile(frame)
    return QualityEngine().run(frame, profile), profile


def keys(findings) -> set[str]:
    return {f.check_key for f in findings}


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #
class TestQualityChecks:
    def test_detects_missing_values(self) -> None:
        findings, _ = run_checks(pd.DataFrame({"a": [1, None, 3], "b": [1, 2, 3]}))
        missing = [f for f in findings if f.check_key == "missing_values"]
        assert missing and missing[0].column_name == "a"
        assert missing[0].count == 1

    def test_detects_duplicate_rows(self) -> None:
        frame = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
        findings, _ = run_checks(frame)
        duplicates = [f for f in findings if f.check_key == "duplicate_rows"]
        assert duplicates and duplicates[0].count == 1

    def test_detects_blank_strings(self) -> None:
        findings, _ = run_checks(pd.DataFrame({"a": ["x", "   ", ""], "b": [1, 2, 3]}))
        assert "blank_strings" in keys(findings)

    def test_detects_leading_and_trailing_spaces(self) -> None:
        findings, _ = run_checks(pd.DataFrame({"a": ["  x", "y  ", "z"], "b": [1, 2, 3]}))
        assert "whitespace" in keys(findings)

    def test_detects_case_inconsistency(self) -> None:
        frame = pd.DataFrame({"state": ["Texas", "texas", "TEXAS", "Ohio"], "n": [1, 2, 3, 4]})
        findings, _ = run_checks(frame)
        assert "case_inconsistency" in keys(findings)

    def test_detects_invalid_emails(self) -> None:
        frame = pd.DataFrame({"email": ["a@x.com", "bad@@", "c@x.com", "nope"]})
        findings, _ = run_checks(frame)
        assert "invalid_email" in keys(findings)

    def test_detects_constant_column(self) -> None:
        findings, _ = run_checks(pd.DataFrame({"same": ["x"] * 5, "n": range(5)}))
        assert "constant_column" in keys(findings)

    def test_detects_duplicate_columns(self) -> None:
        frame = pd.DataFrame({"a": [1, 2, 3], "copy": [1, 2, 3]})
        findings, _ = run_checks(frame)
        duplicates = [f for f in findings if f.check_key == "duplicate_columns"]
        assert duplicates, "identical columns should be reported"

    def test_detects_negative_values_in_amount_column(self) -> None:
        frame = pd.DataFrame({"amount": [10.0, -5.0, 20.0], "n": [1, 2, 3]})
        findings, _ = run_checks(frame)
        assert "negative_values" in keys(findings)

    def test_detects_outliers(self) -> None:
        # Spread the bulk of the values so the column isn't flagged as
        # low-cardinality instead, which would mask the outlier check.
        frame = pd.DataFrame({"v": [float(i) for i in range(60)] + [50_000.0]})
        findings, _ = run_checks(frame)
        assert "outliers" in keys(findings)

    def test_empty_dataset_is_reported(self) -> None:
        findings, _ = run_checks(pd.DataFrame({"a": []}))
        assert "empty_dataset" in keys(findings)

    def test_clean_frame_produces_no_critical_findings(self) -> None:
        frame = pd.DataFrame({
            "id": [1, 2, 3, 4],
            "region": ["North", "South", "East", "West"],
            "sales": [10.5, 20.5, 30.5, 40.5],
        })
        findings, _ = run_checks(frame)
        assert not [f for f in findings if f.severity == Severity.CRITICAL]

    def test_every_finding_carries_a_valid_dimension_and_severity(self, messy_frame) -> None:
        findings, _ = run_checks(messy_frame)
        assert findings, "the messy fixture must produce findings"
        for finding in findings:
            assert finding.dimension in set(Dimension)
            assert finding.severity in set(Severity)
            assert finding.count >= 0


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
class TestScorer:
    def test_score_is_bounded(self, messy_frame) -> None:
        findings, profile = run_checks(messy_frame)
        score = Scorer().score(findings, profile, messy_frame)
        assert 0 <= score.overall <= 100
        for value in score.dimensions.values():
            assert 0 <= value <= 100

    def test_clean_data_scores_higher_than_messy(self, messy_frame) -> None:
        clean = pd.DataFrame({
            "id": range(20),
            "region": ["North", "South"] * 10,
            "sales": [float(i) for i in range(20)],
        })
        clean_findings, clean_profile = run_checks(clean)
        messy_findings, messy_profile = run_checks(messy_frame)
        clean_score = Scorer().score(clean_findings, clean_profile, clean).overall
        messy_score = Scorer().score(messy_findings, messy_profile, messy_frame).overall
        assert clean_score > messy_score

    def test_no_findings_scores_full_marks(self) -> None:
        frame = pd.DataFrame({"a": [1, 2, 3]})
        _, profile = run_checks(frame)
        assert Scorer().score([], profile, frame).overall == 100

    def test_reports_all_six_dimensions(self, messy_frame) -> None:
        findings, profile = run_checks(messy_frame)
        dims = Scorer().score(findings, profile, messy_frame).dimensions
        assert set(dims) == {d.value for d in Dimension}

    def test_counts_duplicate_rows_and_total_issues(self, messy_frame) -> None:
        findings, profile = run_checks(messy_frame)
        score = Scorer().score(findings, profile, messy_frame)
        assert score.total_issues == len(findings)
        assert score.duplicate_rows >= 1

    def test_overall_never_exceeds_any_dimension(self, messy_frame) -> None:
        """Overall is the union over all checks, so it is the floor of the six."""
        findings, profile = run_checks(messy_frame)
        score = Scorer().score(findings, profile, messy_frame)
        assert all(score.overall <= v for v in score.dimensions.values())

    def test_a_row_failing_two_checks_is_counted_once(self) -> None:
        """Two problems on the same row must cost the same as one."""
        one = pd.DataFrame({"a": [None, 1, 2, 3], "b": ["x", "y", "z", "w"]})
        two = pd.DataFrame({"a": [None, 1, 2, 3], "b": [" x ", "y", "z", "w"]})
        scorer = Scorer()
        f1, p1 = run_checks(one)
        f2, p2 = run_checks(two)
        assert len(f2) > len(f1)  # the whitespace finding is genuinely extra
        assert scorer.score(f1, p1, one).overall == scorer.score(f2, p2, two).overall

    def test_column_level_checks_do_not_dirty_rows(self) -> None:
        """A constant column is an issue but must not zero the score."""
        frame = pd.DataFrame({"id": range(30), "flag": ["same"] * 30})
        findings, profile = run_checks(frame)
        assert "constant_column" in keys(findings)
        assert Scorer().score(findings, profile, frame).overall == 100

    def test_empty_dataset_scores_zero(self) -> None:
        frame = pd.DataFrame({"a": []})
        findings, profile = run_checks(frame)
        assert Scorer().score(findings, profile, frame).overall == 0


# --------------------------------------------------------------------------- #
# Explanations
# --------------------------------------------------------------------------- #
class TestExplanations:
    def test_names_the_real_column_and_count(self) -> None:
        result = explain_issue("missing_values", "revenue", 42, 500)
        assert "revenue" in result["why"]
        assert "42" in result["why"]
        assert "500" in result["why"]

    def test_reports_percentage_of_affected_rows(self) -> None:
        result = explain_issue("missing_values", "revenue", 50, 200)
        assert "25.0%" in result["why"] or "25%" in result["why"]

    def test_business_impact_and_fix_are_populated(self) -> None:
        result = explain_issue("missing_values", "revenue", 1, 10)
        assert result["business_impact"]
        assert "revenue" in result["recommended_fix"]

    def test_confidence_is_none_because_it_is_deterministic(self) -> None:
        assert explain_issue("missing_values", "a", 1, 10)["confidence"] is None

    def test_unknown_check_key_still_returns_a_usable_shape(self) -> None:
        result = explain_issue("not_a_real_check", "a", 1, 10)
        assert set(result) >= {"why", "business_impact", "recommended_fix", "confidence"}

    def test_column_less_finding_is_phrased_without_a_column(self) -> None:
        result = explain_issue("duplicate_rows", None, 3, 100)
        assert "3 rows" in result["why"]

    @pytest.mark.parametrize("check_key", sorted(FIXABLE_CHECKS))
    def test_every_fixable_check_has_an_explanation(self, check_key: str) -> None:
        result = explain_issue(check_key, "col", 2, 10)
        assert result["business_impact"], f"{check_key} has no business impact text"


# --------------------------------------------------------------------------- #
# Fixes
# --------------------------------------------------------------------------- #
class TestFixer:
    def test_fills_missing_numeric_with_median(self) -> None:
        frame = pd.DataFrame({"v": [10.0, None, 30.0]})
        result = apply_fix(frame, "missing_values", "v")
        assert result.df["v"].isna().sum() == 0
        assert result.rows_affected == 1
        assert result.df["v"].tolist() == [10.0, 20.0, 30.0]

    def test_fills_missing_text_with_most_frequent(self) -> None:
        frame = pd.DataFrame({"c": ["a", "a", None]})
        result = apply_fix(frame, "missing_values", "c")
        assert result.df["c"].tolist() == ["a", "a", "a"]

    def test_strips_whitespace(self) -> None:
        frame = pd.DataFrame({"c": ["  x  ", "y"]})
        result = apply_fix(frame, "whitespace", "c")
        assert result.df["c"].tolist() == ["x", "y"]

    def test_drops_duplicate_rows(self) -> None:
        frame = pd.DataFrame({"a": [1, 1, 2]})
        result = apply_fix(frame, "duplicate_rows", None)
        assert len(result.df) == 2
        assert result.rows_affected == 1

    def test_blank_strings_are_imputed_not_left_empty(self) -> None:
        """Blanks become the column's most-frequent value, not NULL.

        The panel offers this as a repair, so the column ends up usable rather
        than merely honest about being empty.
        """
        frame = pd.DataFrame({"c": ["x", "   ", ""]})
        result = apply_fix(frame, "blank_strings", "c")
        assert result.df["c"].tolist() == ["x", "x", "x"]
        assert result.rows_affected == 2

    def test_normalizes_case_inconsistency(self) -> None:
        frame = pd.DataFrame({"c": ["Texas", "texas", "TEXAS"]})
        result = apply_fix(frame, "case_inconsistency", "c")
        assert result.df["c"].nunique() == 1

    def test_unknown_check_is_rejected(self) -> None:
        with pytest.raises(UnfixableIssueError):
            apply_fix(pd.DataFrame({"a": [1]}), "not_fixable", "a")

    def test_fix_never_mutates_the_input_frame(self) -> None:
        frame = pd.DataFrame({"v": [10.0, None, 30.0]})
        apply_fix(frame, "missing_values", "v")
        assert frame["v"].isna().sum() == 1, "the original frame must be untouched"

    def test_fix_reports_how_many_rows_it_touched(self) -> None:
        frame = pd.DataFrame({"c": ["  x  ", "  y  ", "z"]})
        result = apply_fix(frame, "whitespace", "c")
        assert result.rows_affected == 2
        assert result.op and result.detail

    def test_contact_columns_are_never_imputed_with_a_guess(self) -> None:
        """A fabricated email is worse than a missing one.

        Contact and identifier columns drop the affected rows instead of
        inheriting the most-frequent value, which would invent a real-looking
        address for someone who never gave one.
        """
        frame = pd.DataFrame({"email": ["a@x.com", "a@x.com", None]})
        result = apply_fix(frame, "missing_values", "email")
        assert len(result.df) == 2
        assert "a@x.com" not in result.df["email"].tolist()[2:]
        assert result.df["email"].isna().sum() == 0
