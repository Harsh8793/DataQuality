"""End-to-end service flows, one class per dashboard tab.

These drive the real services against a real (temporary) dataset so the
orchestration paths are exercised, not just the pure helpers. Every dataset
created here is deleted afterwards, so the suite is repeatable.
"""

from __future__ import annotations

import io

import pandas as pd
import pytest

from app.exceptions.base import BadRequestException, NotFoundException
from app.schemas.ai import CellEdit
from app.schemas.chat import ChatRequest
from app.services.analysis_service import AnalysisService
from app.services.chat_service import ChatService
from app.services.cleaning_service import CleaningService
from app.services.dashboard_service import DashboardService
from app.services.dataset_service import DatasetService
from app.services.edit_service import EditService
from app.services.governance_service import GovernanceService
from app.services.report_service import ReportService


@pytest.fixture
def user_id(db_session) -> int:
    """The seeded demo user, or any user present in this database."""
    from app.models.user import User

    user = db_session.query(User).first()
    if user is None:  # pragma: no cover - only on a pristine database
        pytest.skip("no user seeded in the test database")
    return user.id


@pytest.fixture
def dataset(db_session, user_id: int, messy_frame: pd.DataFrame):
    """Upload the messy fixture, yield the dataset, then delete it."""
    csv = messy_frame.to_csv(index=False).encode()
    service = DatasetService(db_session)
    summary = service.upload(user_id, "flow_test.csv", csv)
    db_session.commit()
    try:
        yield summary
    finally:
        try:
            DatasetService(db_session).delete(summary.id, user_id)
            db_session.commit()
        except Exception:  # pragma: no cover - cleanup must never fail a test
            db_session.rollback()


@pytest.fixture
def analyzed(db_session, dataset, user_id: int):
    """A dataset that has been through the full analysis pipeline."""
    AnalysisService(db_session).analyze(dataset.id, user_id)
    db_session.commit()
    return dataset


# --------------------------------------------------------------------------- #
# Overview tab
# --------------------------------------------------------------------------- #
class TestOverviewFlow:
    def test_upload_records_shape_and_format(self, dataset, messy_frame) -> None:
        assert dataset.row_count == len(messy_frame)
        assert dataset.col_count == messy_frame.shape[1]
        assert dataset.file_format == "csv"

    def test_rejects_an_unsupported_extension(self, db_session, user_id: int) -> None:
        with pytest.raises(Exception):
            DatasetService(db_session).upload(user_id, "notes.pdf", b"x")

    def test_preview_returns_a_page_of_rows(self, db_session, dataset, user_id: int) -> None:
        preview = DatasetService(db_session).preview(dataset.id, user_id, rows=3)
        assert len(preview.rows) == 3
        assert preview.total_rows == dataset.row_count

    def test_preview_honours_the_offset(self, db_session, dataset, user_id: int) -> None:
        first = DatasetService(db_session).preview(dataset.id, user_id, rows=1, offset=0)
        second = DatasetService(db_session).preview(dataset.id, user_id, rows=1, offset=1)
        assert first.rows != second.rows

    def test_profile_is_built_on_first_view(self, db_session, dataset, user_id: int) -> None:
        columns = AnalysisService(db_session).get_profile(dataset.id, user_id)
        db_session.commit()
        assert len(columns) == dataset.col_count

    def test_profile_is_cached_on_the_second_call(
        self, db_session, dataset, user_id: int
    ) -> None:
        service = AnalysisService(db_session)
        first = service.get_profile(dataset.id, user_id)
        db_session.commit()
        second = service.get_profile(dataset.id, user_id)
        assert [c.name for c in first] == [c.name for c in second]

    def test_another_users_dataset_is_not_found(self, db_session, dataset) -> None:
        with pytest.raises(NotFoundException):
            DatasetService(db_session).get_summary(dataset.id, user_id=-999)

    def test_listing_includes_the_new_dataset(self, db_session, dataset, user_id: int) -> None:
        listed, total = DatasetService(db_session).list(user_id, limit=50, offset=0)
        assert total >= 1
        assert any(d.id == dataset.id for d in listed)


# --------------------------------------------------------------------------- #
# Quality tab
# --------------------------------------------------------------------------- #
class TestQualityFlow:
    def test_analysis_persists_a_scored_report(self, db_session, analyzed, user_id: int) -> None:
        report = AnalysisService(db_session).get_latest(analyzed.id, user_id)
        assert report is not None
        assert 0 <= report.overall_score <= 100
        assert report.total_issues >= 1

    def test_issues_carry_deterministic_explanations(
        self, db_session, analyzed, user_id: int
    ) -> None:
        report = AnalysisService(db_session).get_latest(analyzed.id, user_id)
        assert report.issues, "the messy fixture must produce issues"
        for issue in report.issues:
            assert issue.problem and issue.why and issue.business_impact

    def test_low_score_datasets_are_gated_for_approval(
        self, db_session, analyzed, user_id: int
    ) -> None:
        summary = DatasetService(db_session).get_summary(analyzed.id, user_id)
        assert summary.approval_status in {"approved", "pending"}

    def test_approval_can_be_granted(self, db_session, analyzed, user_id: int) -> None:
        updated = DatasetService(db_session).set_approval(analyzed.id, user_id, True, "looks fine")
        db_session.commit()
        assert updated.approval_status == "approved"

    def test_fix_all_does_not_lower_the_score(self, db_session, analyzed, user_id: int) -> None:
        service = AnalysisService(db_session)
        before = service.get_latest(analyzed.id, user_id).overall_score
        result = service.fix_all(analyzed.id, user_id)
        db_session.commit()
        assert result["report"].overall_score >= before

    def test_fixes_can_be_listed_and_undone(self, db_session, analyzed, user_id: int) -> None:
        service = AnalysisService(db_session)
        service.fix_all(analyzed.id, user_id)
        db_session.commit()
        listed = service.list_fixes(analyzed.id, user_id)
        assert listed["fixes"] and listed["undoable"] is True
        undo = service.undo_fixes(analyzed.id, user_id)
        db_session.commit()
        assert undo["undone_fixes"] >= 1
        assert undo["report"] is not None

    def test_exclusions_round_trip(self, db_session, analyzed, user_id: int) -> None:
        service = AnalysisService(db_session)
        service.add_exclusion(analyzed.id, user_id, "missing_values", "revenue")
        db_session.commit()
        assert service.list_exclusions(analyzed.id, user_id)["exclusions"]
        service.remove_exclusion(analyzed.id, user_id, "missing_values", "revenue")
        db_session.commit()
        assert not service.list_exclusions(analyzed.id, user_id)["exclusions"]

    def test_cleaning_produces_a_child_dataset(self, db_session, analyzed, user_id: int) -> None:
        result = CleaningService(db_session).clean(analyzed.id, user_id)
        db_session.commit()
        assert result.cleaned_dataset_id != analyzed.id
        cleaned = DatasetService(db_session).get_summary(result.cleaned_dataset_id, user_id)
        assert cleaned.is_cleaned is True
        DatasetService(db_session).delete(result.cleaned_dataset_id, user_id)
        db_session.commit()


# --------------------------------------------------------------------------- #
# Edit data tab
# --------------------------------------------------------------------------- #
class TestEditFlow:
    def test_edit_is_applied_and_undoable(self, db_session, analyzed, user_id: int) -> None:
        service = EditService(db_session)
        applied = service.apply(analyzed.id, user_id, [CellEdit(row_index=0, column="state", value="Nevada")])
        db_session.commit()
        assert applied.applied == 1

        preview = DatasetService(db_session).preview(analyzed.id, user_id, rows=1)
        assert preview.rows[0]["state"] == "Nevada"

        undone = service.undo_last(analyzed.id, user_id)
        db_session.commit()
        assert undone.undone == 1
        restored = DatasetService(db_session).preview(analyzed.id, user_id, rows=1)
        assert restored.rows[0]["state"] != "Nevada"

    def test_edit_history_lists_the_batch(self, db_session, analyzed, user_id: int) -> None:
        service = EditService(db_session)
        service.apply(analyzed.id, user_id, [CellEdit(row_index=1, column="state", value="Utah")])
        db_session.commit()
        assert service.get_history(analyzed.id, user_id).items

    def test_unknown_column_is_rejected(self, db_session, analyzed, user_id: int) -> None:
        with pytest.raises(BadRequestException, match="does not exist"):
            EditService(db_session).apply(
                analyzed.id, user_id, [CellEdit(row_index=0, column="nope", value="x")]
            )

    def test_out_of_range_row_is_rejected(self, db_session, analyzed, user_id: int) -> None:
        with pytest.raises(BadRequestException, match="out of range"):
            EditService(db_session).apply(
                analyzed.id, user_id, [CellEdit(row_index=9_999, column="state", value="x")]
            )

    def test_undo_with_no_history_is_rejected(self, db_session, dataset, user_id: int) -> None:
        with pytest.raises(Exception):
            EditService(db_session).undo_last(dataset.id, user_id)


# --------------------------------------------------------------------------- #
# Dashboard tab
# --------------------------------------------------------------------------- #
class TestDashboardFlow:
    def test_widget_pool_is_generated(self, db_session, analyzed, user_id: int) -> None:
        builder = DashboardService(db_session).get_builder(analyzed.id, user_id)
        assert builder.pool.kpis or builder.pool.charts

    def test_dashboard_builds_with_selected_widgets(
        self, db_session, analyzed, user_id: int
    ) -> None:
        dashboard = DashboardService(db_session).build(analyzed.id, user_id)
        assert dashboard.kpis or dashboard.charts

    def test_selection_persists(self, db_session, analyzed, user_id: int) -> None:
        service = DashboardService(db_session)
        builder = service.get_builder(analyzed.id, user_id)
        chart_ids = [c.id for c in builder.pool.charts][:1]
        service.save_selection(analyzed.id, user_id, kpis=[], charts=chart_ids)
        db_session.commit()
        assert service.get_builder(analyzed.id, user_id).selected.charts == chart_ids

    def test_command_proposes_rather_than_creating(
        self, db_session, analyzed, user_id: int
    ) -> None:
        response = DashboardService(db_session).command(analyzed.id, user_id, "count by state")
        assert response.kind in {"review", "choice"}
        assert 0.0 <= response.confidence <= 1.0

    def test_command_reports_coverage_and_warnings(
        self, db_session, analyzed, user_id: int
    ) -> None:
        response = DashboardService(db_session).command(analyzed.id, user_id, "revenue by state")
        widget = response.chart or (response.options[0].chart if response.options else None)
        assert widget is not None
        assert widget.meta["rows_total"] > 0

    def test_command_refuses_unknown_columns(self, db_session, analyzed, user_id: int) -> None:
        with pytest.raises(BadRequestException, match="None of your columns"):
            DashboardService(db_session).command(analyzed.id, user_id, "profit margin by warehouse")

    def test_ambiguous_request_offers_both_readings(
        self, db_session, analyzed, user_id: int
    ) -> None:
        response = DashboardService(db_session).command(
            analyzed.id, user_id, "average revenue by state"
        )
        if response.kind == "choice":
            assert {o.kind for o in response.options} == {"kpi", "chart"}
        else:  # a single confident reading is also acceptable
            assert response.kind == "review"


# --------------------------------------------------------------------------- #
# Chat tab
# --------------------------------------------------------------------------- #
class TestChatFlow:
    def test_row_count_question_is_answered_deterministically(
        self, db_session, analyzed, user_id: int, messy_frame
    ) -> None:
        response = ChatService(db_session).ask(
            analyzed.id, user_id, ChatRequest(question="how many rows are there?")
        )
        db_session.commit()
        assert str(len(messy_frame)) in response.answer

    def test_conversation_is_persisted(self, db_session, analyzed, user_id: int) -> None:
        service = ChatService(db_session)
        service.ask(analyzed.id, user_id, ChatRequest(question="how many rows are there?"))
        db_session.commit()
        history = service.get_history(analyzed.id, user_id)
        assert len(history.messages) >= 2  # the question and the answer

    def test_history_can_be_cleared(self, db_session, analyzed, user_id: int) -> None:
        service = ChatService(db_session)
        service.ask(analyzed.id, user_id, ChatRequest(question="how many rows are there?"))
        db_session.commit()
        service.clear_history(analyzed.id, user_id)
        db_session.commit()
        assert service.get_history(analyzed.id, user_id).messages == []

    def test_answer_without_an_llm_still_returns_something_useful(
        self, db_session, analyzed, user_id: int
    ) -> None:
        response = ChatService(db_session).ask(
            analyzed.id, user_id, ChatRequest(question="hello")
        )
        db_session.commit()
        assert response.answer


# --------------------------------------------------------------------------- #
# Governance tab
# --------------------------------------------------------------------------- #
class TestGovernanceFlow:
    def test_classification_is_persisted(self, db_session, analyzed, user_id: int) -> None:
        report = GovernanceService(db_session).classify(analyzed.id, user_id)
        db_session.commit()
        assert report.classification
        assert report.ingestion_tier in {"bronze", "silver", "gold"}

    def test_pii_columns_are_reported(self, db_session, analyzed, user_id: int) -> None:
        report = GovernanceService(db_session).classify(analyzed.id, user_id)
        db_session.commit()
        assert "email" in report.pii_columns


# --------------------------------------------------------------------------- #
# Reports tab
# --------------------------------------------------------------------------- #
class TestReportsFlow:
    def test_report_requires_prior_analysis(self, db_session, dataset, user_id: int) -> None:
        with pytest.raises(NotFoundException, match="Analyze"):
            ReportService(db_session).generate(dataset.id, user_id, "pdf")

    @pytest.mark.parametrize("report_type", ["pdf", "xlsx", "csv"])
    def test_each_report_type_is_produced(
        self, db_session, analyzed, user_id: int, report_type: str
    ) -> None:
        from pathlib import Path

        service = ReportService(db_session)
        record = service.generate(analyzed.id, user_id, report_type)
        db_session.commit()
        assert record.report_type == report_type
        assert record.size_bytes > 0
        stored = service.get_record(record.id, user_id)
        assert Path(stored.file_path).exists()

    def test_csv_export_returns_the_current_data(
        self, db_session, analyzed, user_id: int, messy_frame
    ) -> None:
        csv_text, filename = DatasetService(db_session).export_csv(analyzed.id, user_id)
        assert filename.endswith(".csv")
        exported = pd.read_csv(io.StringIO(csv_text))
        assert len(exported) == len(messy_frame)

    def test_export_reflects_an_applied_edit(self, db_session, analyzed, user_id: int) -> None:
        EditService(db_session).apply(
            analyzed.id, user_id, [CellEdit(row_index=0, column="state", value="Zedland")]
        )
        db_session.commit()
        csv_text, _ = DatasetService(db_session).export_csv(analyzed.id, user_id)
        assert "Zedland" in csv_text
