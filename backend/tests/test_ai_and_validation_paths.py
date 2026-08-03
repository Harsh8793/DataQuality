"""AI-assisted paths and custom validations.

Completes coverage of ``services/ai_service.py``,
``services/custom_validation_service.py``, ``core/engines/affected.py``,
``core/engines/duckdb_engine.py`` (condition evaluation) and the health
reporting in ``core/llm/groq_client.py``.

Both branches are asserted throughout: what the tab shows when the model
answers, and what it shows when the model is unavailable.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.constants.enums import CompareVerdict, LlmStatus
from app.core.engines.affected import affected_mask
from app.core.engines.duckdb_engine import DuckDBEngine
from app.core.llm.groq_client import GroqLLM
from app.exceptions.base import BadRequestException
from app.schemas.ai import ExplainRequest
from app.services.ai_service import AiService
from app.services.custom_validation_service import CustomValidationService
from app.services.dataset_service import DatasetService

from tests.conftest import scripted_llm


@pytest.fixture
def user_id(db_session) -> int:
    from app.models.user import User

    user = db_session.query(User).first()
    if user is None:  # pragma: no cover
        pytest.skip("no user seeded in the test database")
    return user.id


@pytest.fixture
def dataset(db_session, user_id: int, messy_frame: pd.DataFrame):
    csv = messy_frame.to_csv(index=False).encode()
    summary = DatasetService(db_session).upload(user_id, "ai_paths.csv", csv)
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
# Affected-row masks (Quality tab "show me the rows")
# --------------------------------------------------------------------------- #
class TestAffectedRows:
    def test_missing_values_mask(self) -> None:
        frame = pd.DataFrame({"a": [1, None, 3]})
        assert affected_mask(frame, "missing_values", "a").tolist() == [False, True, False]

    def test_blank_strings_mask(self) -> None:
        frame = pd.DataFrame({"a": ["x", "  ", ""]})
        assert affected_mask(frame, "blank_strings", "a").tolist() == [False, True, True]

    def test_whitespace_mask(self) -> None:
        frame = pd.DataFrame({"a": ["x", " y", "z "]})
        assert affected_mask(frame, "whitespace", "a").tolist() == [False, True, True]

    def test_duplicate_rows_mask(self) -> None:
        frame = pd.DataFrame({"a": [1, 1, 2]})
        assert affected_mask(frame, "duplicate_rows", None).sum() >= 1

    def test_invalid_email_mask(self) -> None:
        frame = pd.DataFrame({"email": ["a@x.com", "bad@@"]})
        assert affected_mask(frame, "invalid_email", "email").tolist() == [False, True]

    def test_unknown_check_selects_nothing(self) -> None:
        frame = pd.DataFrame({"a": [1, 2]})
        assert affected_mask(frame, "not_a_check", "a").sum() == 0

    def test_missing_column_selects_nothing(self) -> None:
        frame = pd.DataFrame({"a": [1, 2]})
        assert affected_mask(frame, "missing_values", "absent").sum() == 0


# --------------------------------------------------------------------------- #
# Condition evaluation (custom validations)
# --------------------------------------------------------------------------- #
class TestConditionEvaluation:
    @pytest.fixture
    def engine(self) -> DuckDBEngine:
        return DuckDBEngine()

    def test_counts_matching_rows(self, engine: DuckDBEngine) -> None:
        frame = pd.DataFrame({"amount": [1.0, -5.0, 10.0]})
        count, indices, columns, rows = engine.evaluate_condition(frame, "amount < 0")
        assert count == 1
        assert indices == [1]
        assert "amount" in columns and rows

    def test_zero_matches_is_not_an_error(self, engine: DuckDBEngine) -> None:
        frame = pd.DataFrame({"amount": [1.0, 2.0]})
        count, indices, _, rows = engine.evaluate_condition(frame, "amount > 100")
        assert count == 0 and indices == [] and rows == []

    def test_rejects_an_empty_condition(self, engine: DuckDBEngine) -> None:
        with pytest.raises(BadRequestException, match="Empty"):
            engine.evaluate_condition(pd.DataFrame({"a": [1]}), "  ")

    def test_rejects_forbidden_sql_in_a_condition(self, engine: DuckDBEngine) -> None:
        with pytest.raises(BadRequestException, match="forbidden"):
            engine.evaluate_condition(pd.DataFrame({"a": [1]}), "1=1; DROP TABLE dataset")

    def test_rejects_a_nonsense_condition(self, engine: DuckDBEngine) -> None:
        with pytest.raises(BadRequestException):
            engine.evaluate_condition(pd.DataFrame({"a": [1]}), "not_a_column > 1")

    def test_sample_limit_caps_returned_rows(self, engine: DuckDBEngine) -> None:
        frame = pd.DataFrame({"a": list(range(50))})
        count, _, _, rows = engine.evaluate_condition(frame, "a >= 0", sample_limit=5)
        assert count == 50
        assert len(rows) <= 5


class TestCustomValidations:
    def test_offline_parser_handles_a_null_rule(self, db_session, dataset, user_id: int) -> None:
        proposal = CustomValidationService(db_session).propose(
            dataset.id, user_id, "flag rows where revenue is missing"
        )
        assert proposal.condition == '"revenue" IS NULL'
        assert proposal.generated_by == "fallback"
        assert proposal.matched_rows >= 1

    def test_offline_parser_handles_a_numeric_comparison(
        self, db_session, dataset, user_id: int
    ) -> None:
        proposal = CustomValidationService(db_session).propose(
            dataset.id, user_id, "flag rows where revenue < 0"
        )
        assert "revenue" in proposal.condition and "<" in proposal.condition
        assert proposal.total_rows > 0

    def test_unparseable_prompt_is_refused_with_guidance(
        self, db_session, dataset, user_id: int
    ) -> None:
        """No column named and no LLM — refuse rather than invent a rule."""
        with pytest.raises(BadRequestException, match="naming a column"):
            CustomValidationService(db_session).propose(
                dataset.id, user_id, "make the data better somehow"
            )

    def test_proposal_uses_the_model_when_available(
        self, db_session, dataset, user_id: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scripted_llm(
            monkeypatch,
            payload={
                "name": "Revenue present",
                "description": "Revenue must be filled in.",
                "dimension": "completeness",
                "severity": "high",
                "condition": '"revenue" IS NULL',
            },
        )
        proposal = CustomValidationService(db_session).propose(
            dataset.id, user_id, "revenue must be filled in"
        )
        assert "revenue" in proposal.condition.lower()

    def test_created_rule_can_be_listed_and_deleted(
        self, db_session, dataset, user_id: int
    ) -> None:
        service = CustomValidationService(db_session)
        proposal = service.propose(dataset.id, user_id, "flag rows where revenue is missing")
        created = service.create(dataset.id, user_id, proposal)
        db_session.commit()

        assert any(v.id == created.id for v in service.list(dataset.id, user_id))
        service.delete(dataset.id, created.id, user_id)
        db_session.commit()
        assert not any(v.id == created.id for v in service.list(dataset.id, user_id))

    def test_an_invalid_condition_is_rejected_on_create(
        self, db_session, dataset, user_id: int
    ) -> None:
        service = CustomValidationService(db_session)
        proposal = service.propose(dataset.id, user_id, "flag rows where revenue is missing")
        proposal.condition = "this is not sql"
        with pytest.raises(BadRequestException):
            service.create(dataset.id, user_id, proposal)


# --------------------------------------------------------------------------- #
# AI service: explain, story, compare, suggestions
# --------------------------------------------------------------------------- #
class TestExplainWidget:
    def test_falls_back_to_a_deterministic_kpi_explanation(
        self, db_session, dataset, user_id: int
    ) -> None:
        request = ExplainRequest(kind="kpi", label="Avg revenue", value=6330.36, format="currency")
        response = AiService(db_session).explain_widget(dataset.id, user_id, request)
        assert response.generated_by == "fallback"
        assert "Avg revenue" in response.explanation

    def test_falls_back_for_a_chart_and_names_the_extremes(
        self, db_session, dataset, user_id: int
    ) -> None:
        request = ExplainRequest(
            kind="chart", label="Revenue by state", chart_type="bar", x="state", y="revenue",
            data=[{"name": "CA", "value": 100}, {"name": "TX", "value": 5}],
        )
        response = AiService(db_session).explain_widget(dataset.id, user_id, request)
        assert "CA" in response.explanation and "TX" in response.explanation

    def test_uses_the_model_when_it_answers(
        self, db_session, dataset, user_id: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scripted_llm(monkeypatch, text="Revenue averages about $6,330 per order.")
        request = ExplainRequest(kind="kpi", label="Avg revenue", value=6330.36)
        response = AiService(db_session).explain_widget(dataset.id, user_id, request)
        assert response.generated_by == "ai"


class TestDataStory:
    def test_story_falls_back_and_is_cached(self, db_session, dataset, user_id: int) -> None:
        service = AiService(db_session)
        first = service.get_story(dataset.id, user_id)
        db_session.commit()
        assert first.generated_by == "fallback"
        assert first.story.startswith("•")

        second = service.get_story(dataset.id, user_id)
        assert second.generated_by == "cached"
        assert second.story == first.story

    def test_refresh_regenerates_the_story(
        self, db_session, dataset, user_id: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service = AiService(db_session)
        service.get_story(dataset.id, user_id)
        db_session.commit()

        scripted_llm(monkeypatch, text="• Quality — a fresh AI story.")
        refreshed = AiService(db_session).get_story(dataset.id, user_id, refresh=True)
        db_session.commit()
        assert refreshed.generated_by == "ai"
        assert "fresh AI story" in refreshed.story


class TestChatSuggestions:
    def test_suggestions_reference_real_columns(
        self, db_session, dataset, user_id: int, messy_frame: pd.DataFrame
    ) -> None:
        response = AiService(db_session).chat_suggestions(dataset.id, user_id)
        assert response.questions
        joined = " ".join(response.questions).lower()
        assert any(column.lower() in joined for column in messy_frame.columns)


class TestCompare:
    @pytest.fixture
    def second_dataset(self, db_session, user_id: int, messy_frame: pd.DataFrame):
        frame = messy_frame.copy()
        frame["revenue"] = frame["revenue"].fillna(0) * 2
        csv = frame.to_csv(index=False).encode()
        summary = DatasetService(db_session).upload(user_id, "compare_b.csv", csv)
        db_session.commit()
        try:
            yield summary
        finally:
            try:
                DatasetService(db_session).delete(summary.id, user_id)
                db_session.commit()
            except Exception:  # pragma: no cover
                db_session.rollback()

    def test_reports_row_and_column_counts_for_both_sides(
        self, db_session, dataset, second_dataset, user_id: int
    ) -> None:
        result = AiService(db_session).compare(dataset.id, second_dataset.id, user_id)
        assert result.left_rows == dataset.row_count
        assert result.right_rows == second_dataset.row_count

    def test_verdict_is_unknown_until_both_sides_are_scored(
        self, db_session, dataset, second_dataset, user_id: int
    ) -> None:
        result = AiService(db_session).compare(dataset.id, second_dataset.id, user_id)
        assert result.verdict == CompareVerdict.UNKNOWN
        assert "not been quality-scored" in result.verdict_reason

    def test_narrative_falls_back_to_four_bullets(
        self, db_session, dataset, second_dataset, user_id: int
    ) -> None:
        result = AiService(db_session).compare(dataset.id, second_dataset.id, user_id)
        assert result.generated_by == "fallback"
        lines = [line for line in result.narrative.splitlines() if line.strip()]
        assert len(lines) == 4
        assert all(line.startswith("• ") for line in lines)

    def test_detects_added_and_removed_columns(
        self, db_session, dataset, user_id: int, messy_frame: pd.DataFrame
    ) -> None:
        frame = messy_frame.drop(columns=["quantity"]).assign(discount=1)
        csv = frame.to_csv(index=False).encode()
        other = DatasetService(db_session).upload(user_id, "compare_c.csv", csv)
        db_session.commit()
        try:
            result = AiService(db_session).compare(dataset.id, other.id, user_id)
            assert "discount" in result.added_columns
            assert "quantity" in result.removed_columns
        finally:
            DatasetService(db_session).delete(other.id, user_id)
            db_session.commit()


class TestCompareVerdicts:
    """The verdict is computed from numbers, never taken from the model."""

    @staticmethod
    def _shift(column: str, left_null: float, right_null: float):
        from app.schemas.ai import ColumnShift

        return ColumnShift(column=column, left_null_pct=left_null, right_null_pct=right_null)

    def test_clear_improvement(self) -> None:
        verdict, reason = AiService._compare_verdict(12.0, [], [], [])
        assert verdict == CompareVerdict.IMPROVED
        assert "+12.0" in reason

    def test_improvement_with_new_gaps_is_mixed(self) -> None:
        verdict, reason = AiService._compare_verdict(12.0, [self._shift("email", 0.0, 30.0)], [], [])
        assert verdict == CompareVerdict.MIXED
        assert "email" in reason

    def test_clear_regression(self) -> None:
        verdict, reason = AiService._compare_verdict(-9.0, [], [], [])
        assert verdict == CompareVerdict.REGRESSED
        assert "review before promoting" in reason

    def test_flat_score_with_removed_columns_is_mixed(self) -> None:
        verdict, reason = AiService._compare_verdict(0.0, [], [], ["quantity"])
        assert verdict == CompareVerdict.MIXED
        assert "quantity" in reason

    def test_flat_score_with_worse_completeness_is_mixed(self) -> None:
        verdict, _ = AiService._compare_verdict(0.5, [self._shift("email", 1.0, 40.0)], [], [])
        assert verdict == CompareVerdict.MIXED

    def test_flat_score_with_added_columns_is_equivalent(self) -> None:
        verdict, reason = AiService._compare_verdict(0.0, [], ["discount"], [])
        assert verdict == CompareVerdict.EQUIVALENT
        assert "1 new column" in reason

    def test_no_material_change(self) -> None:
        verdict, reason = AiService._compare_verdict(0.0, [], [], [])
        assert verdict == CompareVerdict.EQUIVALENT
        assert "No material change" in reason

    def test_unscored_side_yields_unknown(self) -> None:
        verdict, _ = AiService._compare_verdict(None, [], [], [])
        assert verdict == CompareVerdict.UNKNOWN


# --------------------------------------------------------------------------- #
# LLM health (the AI Copilot tile)
# --------------------------------------------------------------------------- #
class TestLlmHealth:
    def test_disabled_in_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = GroqLLM()
        monkeypatch.setattr(llm._settings, "llm_enabled", False)
        assert llm.health.status == LlmStatus.DISABLED

    def test_no_key_is_unconfigured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = GroqLLM()
        monkeypatch.setattr(llm._settings, "llm_enabled", True)
        llm._client = None
        assert llm.health.status == LlmStatus.UNCONFIGURED

    def test_configured_but_unproven_says_so(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = GroqLLM()
        monkeypatch.setattr(llm._settings, "llm_enabled", True)
        llm._client = object()
        health = llm.health
        assert health.status == LlmStatus.ACTIVE
        assert "no calls yet" in health.detail

    def test_a_failed_call_degrades_the_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = GroqLLM()
        monkeypatch.setattr(llm._settings, "llm_enabled", True)
        llm._client = object()
        llm._record_failure(RuntimeError("connection reset"))
        health = llm.health
        assert health.status == LlmStatus.DEGRADED
        assert "connection reset" in health.detail

    def test_a_later_success_clears_the_degraded_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        llm = GroqLLM()
        monkeypatch.setattr(llm._settings, "llm_enabled", True)
        llm._client = object()
        llm._record_failure(RuntimeError("boom"))
        llm._record_success()
        assert llm.health.status == LlmStatus.ACTIVE
        assert "Connected to" in llm.health.detail

    def test_unavailable_client_returns_none_rather_than_raising(self) -> None:
        llm = GroqLLM()
        llm._client = None
        assert llm.complete("sys", "user") is None
        assert llm.complete_json("sys", "user") is None
        assert list(llm.stream("sys", "user")) == []

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ('{"a": 1}', {"a": 1}),
            ('```json\n{"a": 1}\n```', {"a": 1}),
            ('prose then {"a": 1} trailing', {"a": 1}),
            ("not json at all", None),
        ],
    )
    def test_json_extraction_handles_model_formatting(self, raw: str, expected) -> None:
        assert GroqLLM._parse_json(raw) == expected
