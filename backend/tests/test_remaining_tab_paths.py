"""The remaining branches behind the Quality and Edit-data tabs.

Targeted at per-issue fixes, row filtering, cleaning comparisons and the full
affected-row mask table — the paths a user reaches by clicking into a specific
issue rather than running the pipeline end to end.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.core.engines.affected import affected_mask
from app.exceptions.base import BadRequestException, NotFoundException
from app.services.analysis_service import AnalysisService
from app.services.cleaning_service import CleaningService
from app.services.dataset_service import DatasetService
from app.services.edit_service import EditService


@pytest.fixture
def user_id(db_session) -> int:
    from app.models.user import User

    user = db_session.query(User).first()
    if user is None:  # pragma: no cover
        pytest.skip("no user seeded in the test database")
    return user.id


@pytest.fixture
def analyzed(db_session, user_id: int, messy_frame: pd.DataFrame):
    csv = messy_frame.to_csv(index=False).encode()
    summary = DatasetService(db_session).upload(user_id, "remaining.csv", csv)
    db_session.commit()
    AnalysisService(db_session).analyze(summary.id, user_id)
    db_session.commit()
    try:
        yield summary
    finally:
        try:
            DatasetService(db_session).delete(summary.id, user_id)
            db_session.commit()
        except Exception:  # pragma: no cover
            db_session.rollback()


# --------------------------------------------------------------------------- #
# Affected-row masks — every branch of the lookup table
# --------------------------------------------------------------------------- #
class TestAffectedMasks:
    @pytest.mark.parametrize(
        ("check_key", "column", "frame", "expected"),
        [
            ("invalid_phone", "phone", pd.DataFrame({"phone": ["+1 555 012 3456", "nope"]}), 1),
            ("invalid_url", "url", pd.DataFrame({"url": ["https://a.com", "nope"]}), 1),
            ("invalid_date", "d", pd.DataFrame({"d": ["2024-01-05", "nope"]}), 1),
            ("negative_values", "v", pd.DataFrame({"v": [1.0, -2.0, -3.0]}), 2),
            ("duplicate_ids", "id", pd.DataFrame({"id": [1, 1, 2]}), 2),
            ("case_inconsistency", "c", pd.DataFrame({"c": ["Tx", "tx", "Oh"]}), 1),
            ("constant_column", "c", pd.DataFrame({"c": ["x", "x", "x"]}), 3),
        ],
    )
    def test_mask_selects_the_expected_rows(
        self, check_key: str, column: str, frame: pd.DataFrame, expected: int
    ) -> None:
        assert int(affected_mask(frame, check_key, column).sum()) == expected

    def test_outlier_mask_flags_the_extreme(self) -> None:
        frame = pd.DataFrame({"v": [float(i) for i in range(40)] + [5_000.0]})
        mask = affected_mask(frame, "outliers", "v")
        assert bool(mask.iloc[-1]) is True

    def test_outlier_mask_is_empty_when_there_is_no_spread(self) -> None:
        frame = pd.DataFrame({"v": [5.0] * 10})
        assert int(affected_mask(frame, "outliers", "v").sum()) == 0

    def test_mask_length_always_matches_the_frame(self) -> None:
        frame = pd.DataFrame({"a": [1, 2, 3]})
        for key in ("missing_values", "outliers", "duplicate_rows", "unknown_key"):
            assert len(affected_mask(frame, key, "a")) == len(frame)


# --------------------------------------------------------------------------- #
# Per-issue fixes (Quality tab, clicking one issue)
# --------------------------------------------------------------------------- #
class TestPerIssueFix:
    def _first_fixable(self, db_session, analyzed, user_id: int):
        report = AnalysisService(db_session).get_latest(analyzed.id, user_id)
        return next((i for i in report.issues if i.fixable), None)

    def test_fixing_one_issue_reanalyzes_the_dataset(
        self, db_session, analyzed, user_id: int
    ) -> None:
        issue = self._first_fixable(db_session, analyzed, user_id)
        if issue is None:  # pragma: no cover - fixture always has fixable issues
            pytest.skip("no fixable issue produced")
        result = AnalysisService(db_session).fix_issue(analyzed.id, issue.id, user_id)
        db_session.commit()
        assert result["report"] is not None
        assert result["rows_affected"] >= 0

    def test_unknown_issue_id_is_rejected(self, db_session, analyzed, user_id: int) -> None:
        with pytest.raises(NotFoundException):
            AnalysisService(db_session).fix_issue(analyzed.id, 10_000_000, user_id)

    def test_undo_without_any_fix_is_rejected(
        self, db_session, analyzed, user_id: int
    ) -> None:
        with pytest.raises(Exception):
            AnalysisService(db_session).undo_fixes(analyzed.id, user_id)

    def _apply_several(self, db_session, analyzed, user_id: int) -> list:
        """Apply each fixable issue as its own fix, returning the fix records."""
        service = AnalysisService(db_session)
        applied = []
        for _ in range(5):
            report = service.get_latest(analyzed.id, user_id)
            issue = next((i for i in report.issues if i.fixable and not i.excluded), None)
            if issue is None:
                break
            applied.append(service.fix_issue(analyzed.id, issue.id, user_id)["fix"])
            db_session.commit()
        return applied

    def test_undoing_one_fix_keeps_the_others(
        self, db_session, analyzed, user_id: int
    ) -> None:
        service = AnalysisService(db_session)
        applied = self._apply_several(db_session, analyzed, user_id)
        if len(applied) < 2:
            pytest.skip("needs at least two independent fixes")

        # A fix is identified by check *and* column: "missing_values" can be
        # fixed separately on several columns.
        def keys() -> set[tuple[str, str | None]]:
            return {
                (f.check_key, f.column_name)
                for f in service.list_fixes(analyzed.id, user_id)["fixes"]
            }

        before = keys()
        target = applied[0]  # the OLDEST fix, not the most recent
        result = service.undo_one_fix(analyzed.id, target.id, user_id)
        db_session.commit()

        assert result["undone_fixes"] == 1
        assert keys() == before - {(target.check_key, target.column_name)}

    def test_undoing_a_middle_fix_does_not_discard_later_ones(
        self, db_session, analyzed, user_id: int
    ) -> None:
        """Regression: a snapshot restore alone would drop every later fix."""
        service = AnalysisService(db_session)
        applied = self._apply_several(db_session, analyzed, user_id)
        if len(applied) < 3:
            pytest.skip("needs at least three independent fixes")

        middle = applied[1]
        service.undo_one_fix(analyzed.id, middle.id, user_id)
        db_session.commit()

        remaining = service.list_fixes(analyzed.id, user_id)["fixes"]
        assert len(remaining) == len(applied) - 1
        assert applied[-1].check_key in {f.check_key for f in remaining}

    def test_undo_all_clears_every_fix_in_one_call(
        self, db_session, analyzed, user_id: int
    ) -> None:
        service = AnalysisService(db_session)
        applied = self._apply_several(db_session, analyzed, user_id)
        if not applied:
            pytest.skip("no fixable issues produced")

        result = service.undo_all_fixes(analyzed.id, user_id)
        db_session.commit()
        assert result["undone_fixes"] == len(applied)
        assert result["remaining_fixes"] == 0
        assert service.list_fixes(analyzed.id, user_id)["fixes"] == []

    def test_undo_all_restores_the_original_row_count(
        self, db_session, analyzed, user_id: int, messy_frame: pd.DataFrame
    ) -> None:
        service = AnalysisService(db_session)
        if not self._apply_several(db_session, analyzed, user_id):
            pytest.skip("no fixable issues produced")
        service.undo_all_fixes(analyzed.id, user_id)
        db_session.commit()
        summary = DatasetService(db_session).get_summary(analyzed.id, user_id)
        assert summary.row_count == len(messy_frame)

    def test_undoing_an_unknown_fix_is_rejected(
        self, db_session, analyzed, user_id: int
    ) -> None:
        with pytest.raises(NotFoundException, match="Fix not found"):
            AnalysisService(db_session).undo_one_fix(analyzed.id, 10_000_000, user_id)

    def test_undo_all_without_any_fix_is_rejected(
        self, db_session, analyzed, user_id: int
    ) -> None:
        with pytest.raises(BadRequestException, match="No fixes to undo"):
            AnalysisService(db_session).undo_all_fixes(analyzed.id, user_id)

    def test_custom_validation_participates_in_analysis(
        self, db_session, analyzed, user_id: int
    ) -> None:
        from app.services.custom_validation_service import CustomValidationService

        validations = CustomValidationService(db_session)
        proposal = validations.propose(analyzed.id, user_id, "flag rows where revenue is missing")
        validations.create(analyzed.id, user_id, proposal)
        db_session.commit()

        report = AnalysisService(db_session).analyze(analyzed.id, user_id)
        db_session.commit()
        assert any("Custom rule" in (i.business_impact or "") for i in report.issues)


# --------------------------------------------------------------------------- #
# Row query + filtered editing (Edit data tab)
# --------------------------------------------------------------------------- #
class TestRowQuery:
    def test_returns_a_page_of_rows(self, db_session, analyzed, user_id: int) -> None:
        result = EditService(db_session).query_rows(analyzed.id, user_id, filter_column=None, filter_op=None, filter_value=None, limit=3, offset=0)
        assert len(result.rows) == 3
        assert result.total_rows > 0
        assert result.columns

    def test_offset_moves_the_window(self, db_session, analyzed, user_id: int) -> None:
        service = EditService(db_session)
        first = service.query_rows(analyzed.id, user_id, filter_column=None, filter_op=None, filter_value=None, limit=1, offset=0)
        second = service.query_rows(analyzed.id, user_id, filter_column=None, filter_op=None, filter_value=None, limit=1, offset=1)
        assert first.row_indices != second.row_indices

    @pytest.mark.parametrize(
        ("op", "value", "column"),
        [
            ("empty", None, "revenue"),
            ("not_empty", None, "revenue"),
            ("equals", "Laptop", "product"),
            ("contains", "Lap", "product"),
        ],
    )
    def test_filters_narrow_the_result(
        self, db_session, analyzed, user_id: int, op: str, value, column: str
    ) -> None:
        result = EditService(db_session).query_rows(
            analyzed.id, user_id,
            filter_column=column, filter_op=op, filter_value=value, limit=50, offset=0,
        )
        assert result.matched_rows <= result.total_rows

    def test_an_unknown_filter_column_is_ignored(
        self, db_session, analyzed, user_id: int
    ) -> None:
        result = EditService(db_session).query_rows(
            analyzed.id, user_id,
            filter_column="nope", filter_op="equals", filter_value="x", limit=5, offset=0,
        )
        assert result.matched_rows == result.total_rows


# --------------------------------------------------------------------------- #
# Cleaning results and comparison (Quality tab)
# --------------------------------------------------------------------------- #
class TestCleaningResults:
    def test_latest_is_returned_after_cleaning(
        self, db_session, analyzed, user_id: int
    ) -> None:
        service = CleaningService(db_session)
        created = service.clean(analyzed.id, user_id)
        db_session.commit()
        try:
            latest = service.get_latest(analyzed.id, user_id)
            assert latest is not None
            assert latest.cleaned_dataset_id == created.cleaned_dataset_id
            assert latest.operations
        finally:
            DatasetService(db_session).delete(created.cleaned_dataset_id, user_id)
            db_session.commit()

    def test_affected_rows_for_one_operation(self, db_session, analyzed, user_id: int) -> None:
        service = CleaningService(db_session)
        created = service.clean(analyzed.id, user_id)
        db_session.commit()
        affected = service.get_op_affected(analyzed.id, 0, user_id)
        assert affected.columns
        assert affected.total_rows >= 0
        DatasetService(db_session).delete(created.cleaned_dataset_id, user_id)
        db_session.commit()

    def test_unknown_operation_index_is_rejected(
        self, db_session, analyzed, user_id: int
    ) -> None:
        service = CleaningService(db_session)
        created = service.clean(analyzed.id, user_id)
        db_session.commit()
        try:
            with pytest.raises(NotFoundException):
                service.get_op_affected(analyzed.id, 9_999, user_id)
        finally:
            DatasetService(db_session).delete(created.cleaned_dataset_id, user_id)
            db_session.commit()

    def test_comparison_workbook_is_produced(self, db_session, analyzed, user_id: int) -> None:
        service = CleaningService(db_session)
        created = service.clean(analyzed.id, user_id)
        db_session.commit()
        try:
            path, filename = service.build_comparison_workbook(analyzed.id, user_id)
            assert filename.endswith(".xlsx")
            assert path.exists() and path.stat().st_size > 0
        finally:
            DatasetService(db_session).delete(created.cleaned_dataset_id, user_id)
            db_session.commit()
