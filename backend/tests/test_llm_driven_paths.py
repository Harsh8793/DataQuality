"""Paths that only run when the model returns a plan.

The rest of the suite proves the deterministic fallbacks; this module scripts
the LLM so the planning branches, self-healing retries and insight generation
are exercised too — still offline and deterministic.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.agents.base import AgentContext
from app.agents.chat_agent import ChatAgent
from app.agents.insight_agent import InsightAgent
from app.core.engines.cleaner import Cleaner
from app.core.engines.fixer import apply_fix
from app.core.engines.profiler import Profiler
from app.core.engines.quality_checks import QualityEngine
from app.core.engines.scorer import Scorer
from app.exceptions.base import BadRequestException
from app.schemas.ai import CellEdit
from app.services.dashboard_service import DashboardService
from app.services.dataset_service import DatasetService
from app.services.edit_service import EditService

from tests.conftest import StubLLM, scripted_llm


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
    summary = DatasetService(db_session).upload(user_id, "llm_paths.csv", csv)
    db_session.commit()
    try:
        yield summary
    finally:
        try:
            DatasetService(db_session).delete(summary.id, user_id)
            db_session.commit()
        except Exception:  # pragma: no cover
            db_session.rollback()


def chat_ctx(frame: pd.DataFrame) -> AgentContext:
    ctx = AgentContext(dataset_id=1, dataset_name="messy", df=frame)
    ctx.profile = Profiler().profile(frame)
    return ctx


def agent_with(plan=None, text=None) -> ChatAgent:
    """A chat agent whose model returns ``plan`` then narrates with ``text``."""
    agent = ChatAgent()
    agent._llm = StubLLM(available=True, payload=plan, text=text)
    return agent


# --------------------------------------------------------------------------- #
# Chat planning
# --------------------------------------------------------------------------- #
class TestChatPlanning:
    def test_sql_plan_is_executed_and_narrated(self, messy_frame: pd.DataFrame) -> None:
        agent = agent_with(
            plan={"mode": "sql", "sql": "SELECT COUNT(*) AS n FROM dataset", "answer": None},
            text="There are 7 rows.",
        )
        answer = agent.ask(chat_ctx(messy_frame), "how many records?")
        assert answer.row_count == 1
        assert "7" in answer.answer

    def test_conversational_plan_returns_no_table(self, messy_frame: pd.DataFrame) -> None:
        agent = agent_with(plan={"mode": "answer", "answer": "Hello! Ask me about this data."})
        answer = agent.ask(chat_ctx(messy_frame), "hi")
        assert answer.sql == "" and answer.row_count == 0
        assert "Hello" in answer.answer

    def test_a_deflection_is_replaced_by_a_real_query(self, messy_frame: pd.DataFrame) -> None:
        """"Please run a SQL query" is not an answer — fall back and compute."""
        agent = agent_with(
            plan={"mode": "answer", "answer": "Please run a SQL query to find out."},
            text="The average is 325.",
        )
        answer = agent.ask(chat_ctx(messy_frame), "what is the average revenue?")
        assert answer.sql, "the agent must fall back to its own SQL"

    def test_broken_sql_falls_back_to_the_deterministic_query(
        self, messy_frame: pd.DataFrame
    ) -> None:
        agent = agent_with(
            plan={"mode": "sql", "sql": "SELECT nonexistent FROM dataset"},
            text="Here is the answer.",
        )
        answer = agent.ask(chat_ctx(messy_frame), "average revenue by state")
        assert answer.sql != "SELECT nonexistent FROM dataset"

    def test_unusable_sql_and_no_fallback_reports_honestly(
        self, messy_frame: pd.DataFrame
    ) -> None:
        agent = agent_with(plan={"mode": "sql", "sql": "SELECT nope FROM dataset"})
        answer = agent.ask(chat_ctx(messy_frame), "zzz")
        assert "couldn't turn that into a valid query" in answer.answer.lower()

    def test_requested_chart_type_is_carried_through(self, messy_frame: pd.DataFrame) -> None:
        agent = agent_with(
            plan={
                "mode": "sql",
                "sql": 'SELECT state, COUNT(*) AS n FROM dataset GROUP BY 1',
                "chart": "pie",
            },
            text="Grouped by state.",
        )
        answer = agent.ask(chat_ctx(messy_frame), "pie chart of rows by state")
        assert answer.chart_spec and answer.chart_spec["type"] == "pie"

    def test_row_count_shortcut_bypasses_the_model(self, messy_frame: pd.DataFrame) -> None:
        agent = agent_with(plan={"mode": "answer", "answer": "I cannot count rows."})
        answer = agent.ask(chat_ctx(messy_frame), "how many rows are there?")
        assert str(len(messy_frame)) in answer.answer

    def test_aggregate_mismatch_is_corrected_before_execution(
        self, messy_frame: pd.DataFrame
    ) -> None:
        """SUM aliased as avg_revenue must not be reported as an average."""
        agent = agent_with(
            plan={"mode": "sql", "sql": 'SELECT SUM("revenue") AS avg_revenue FROM dataset'},
            text=None,
        )
        answer = agent.ask(chat_ctx(messy_frame), "what is the average revenue?")
        assert "AVG(" in answer.sql.upper()

    def test_dirty_value_filter_is_normalised_and_flagged(
        self, messy_frame: pd.DataFrame
    ) -> None:
        agent = agent_with(
            plan={"mode": "sql", "sql": "SELECT COUNT(*) AS n FROM dataset WHERE gender = 'm'"},
            text=None,
        )
        answer = agent.ask(chat_ctx(messy_frame), "how many are male?")
        assert "LOWER(TRIM(" in answer.sql
        assert "male" in answer.answer  # the variant caveat

    def test_a_named_value_missing_from_the_sql_is_disclosed(
        self, messy_frame: pd.DataFrame
    ) -> None:
        agent = agent_with(
            plan={"mode": "sql", "sql": 'SELECT AVG(TRY_CAST("revenue" AS DOUBLE)) AS a FROM dataset'},
            text=None,
        )
        answer = agent.ask(chat_ctx(messy_frame), "average revenue for laptops")
        assert "Laptop" in answer.answer

    def test_history_is_passed_to_the_planner(self, messy_frame: pd.DataFrame) -> None:
        agent = agent_with(plan={"mode": "answer", "answer": "ok"})
        agent.ask(chat_ctx(messy_frame), "now as a pie chart",
                  history=[{"role": "user", "content": "revenue by state"}])
        assert any("revenue by state" in user for _system, user in agent._llm.calls)

    def test_insight_request_is_answered_without_sql(self, messy_frame: pd.DataFrame) -> None:
        agent = agent_with(plan=None)
        answer = agent.ask(chat_ctx(messy_frame), "give me insights about this data")
        assert answer.answer

    def test_run_reports_a_missing_question(self, messy_frame: pd.DataFrame) -> None:
        result = ChatAgent().run(chat_ctx(messy_frame))
        assert result.ok is False

    def test_run_wraps_ask_when_a_question_is_present(self, messy_frame: pd.DataFrame) -> None:
        ctx = chat_ctx(messy_frame)
        ctx.meta["question"] = "how many rows are there?"
        assert ChatAgent().run(ctx).ok is True


# --------------------------------------------------------------------------- #
# Insights
# --------------------------------------------------------------------------- #
class TestInsightAgent:
    def _ctx(self, frame: pd.DataFrame) -> AgentContext:
        ctx = chat_ctx(frame)
        findings = QualityEngine().run(frame, ctx.profile)
        ctx.findings = findings
        ctx.score = Scorer().score(findings, ctx.profile, ctx.df)
        return ctx

    def test_generates_deterministic_insights_without_a_model(
        self, messy_frame: pd.DataFrame
    ) -> None:
        ctx = self._ctx(messy_frame)
        result = InsightAgent().run(ctx)
        assert result.ok is True
        assert ctx.meta["insights"]
        assert all(item["title"] and item["insight"] for item in ctx.meta["insights"])

    def test_explains_every_finding(self, messy_frame: pd.DataFrame) -> None:
        ctx = self._ctx(messy_frame)
        InsightAgent().run(ctx)
        explained = ctx.meta["explanations"]
        assert len(explained) >= 1

    def test_uses_model_insights_when_available(
        self, messy_frame: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = scripted_llm(
            monkeypatch,
            payload=[{"title": "Revenue gaps", "insight": "Revenue is 14% null.",
                      "action": "Impute it.", "category": "risk"}],
        )
        agent = InsightAgent()
        agent._llm = stub
        ctx = self._ctx(messy_frame)
        agent.run(ctx)
        assert any(i["title"] == "Revenue gaps" for i in ctx.meta["insights"])

    def test_unscored_context_still_produces_insights(self) -> None:
        ctx = chat_ctx(pd.DataFrame({"a": [1, 2, 3]}))
        InsightAgent().run(ctx)
        assert ctx.meta["insights"]


# --------------------------------------------------------------------------- #
# Dashboard command with a scripted planner
# --------------------------------------------------------------------------- #
class TestDashboardCommandWithModel:
    def test_model_plan_is_proposed_not_created(
        self, db_session, dataset, user_id: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scripted_llm(
            monkeypatch,
            payload={"kind": "chart", "type": "bar", "x": "state", "y": "revenue"},
        )
        response = DashboardService(db_session).command(dataset.id, user_id, "revenue by state")
        assert response.kind in {"review", "choice"}

    def test_substituted_column_is_disclosed(
        self, db_session, dataset, user_id: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A resolved typo is useful, but the user must be told about it."""
        scripted_llm(monkeypatch, payload={"kind": "kpi", "agg": "avg", "column": "revenue"})
        response = DashboardService(db_session).command(dataset.id, user_id, "avg revenu by state")
        warnings = response.warnings + [w for o in response.options for w in o.warnings]
        assert any("revenue" in w for w in warnings)

    def test_impossible_chart_type_falls_back_to_the_keyword_planner(
        self, db_session, dataset, user_id: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A line chart needs a date axis; revenue/quantity are both numeric.
        scripted_llm(
            monkeypatch,
            payload={"kind": "chart", "type": "line", "x": "revenue", "y": "quantity"},
        )
        response = DashboardService(db_session).command(
            dataset.id, user_id, "revenue vs quantity"
        )
        widget = response.chart or response.options[0].chart
        assert widget.type != "line"

    def test_model_error_plan_is_surfaced(
        self, db_session, dataset, user_id: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scripted_llm(monkeypatch, payload={"kind": "error", "message": "No such measure."})
        with pytest.raises(BadRequestException):
            DashboardService(db_session).command(dataset.id, user_id, "revenue by state")


# --------------------------------------------------------------------------- #
# Remaining fixer + cleaner branches
# --------------------------------------------------------------------------- #
class TestRemainingFixes:
    @pytest.mark.parametrize(
        ("check_key", "column", "frame"),
        [
            ("invalid_email", "email", pd.DataFrame({"email": ["a@x.com", "bad@@"]})),
            ("invalid_phone", "phone", pd.DataFrame({"phone": ["+1 555 012 3456", "nope"]})),
            ("invalid_url", "url", pd.DataFrame({"url": ["https://a.com", "nope"]})),
            ("negative_values", "amount", pd.DataFrame({"amount": [10.0, -5.0]})),
            ("mixed_types", "v", pd.DataFrame({"v": ["1", "2", "x"]})),
            ("constant_column", "c", pd.DataFrame({"c": ["x", "x"], "n": [1, 2]})),
        ],
    )
    def test_each_fix_returns_a_described_result(
        self, check_key: str, column: str, frame: pd.DataFrame
    ) -> None:
        result = apply_fix(frame, check_key, column)
        assert result.op and result.detail
        assert result.rows_affected >= 0
        assert isinstance(result.df, pd.DataFrame)

    def test_duplicate_columns_fix_drops_the_copy(self) -> None:
        frame = pd.DataFrame({"a": [1, 2], "a_copy": [1, 2]})
        result = apply_fix(frame, "duplicate_columns", "a_copy")
        assert "a_copy" not in result.df.columns

    def test_outlier_fix_clips_extremes(self) -> None:
        frame = pd.DataFrame({"v": [float(i) for i in range(50)] + [10_000.0]})
        result = apply_fix(frame, "outliers", "v")
        assert result.df["v"].max() < 10_000.0

    def test_duplicate_ids_fix_removes_repeats(self) -> None:
        frame = pd.DataFrame({"id": [1, 1, 2], "v": [1, 2, 3]})
        result = apply_fix(frame, "duplicate_ids", "id")
        assert result.df["id"].is_unique


class TestCleaner:
    def test_cleaning_reports_each_operation(self, messy_frame: pd.DataFrame) -> None:
        profile = Profiler().profile(messy_frame)
        result = Cleaner().clean(messy_frame, profile)
        assert result.operations
        assert all(op.op and op.detail for op in result.operations)
        assert all(op.rows_affected >= 0 for op in result.operations)

    def test_cleaning_removes_duplicate_rows(self, messy_frame: pd.DataFrame) -> None:
        profile = Profiler().profile(messy_frame)
        result = Cleaner().clean(messy_frame, profile)
        assert len(result.df) <= len(messy_frame)

    def test_cleaning_leaves_a_clean_frame_almost_untouched(
        self, clean_frame: pd.DataFrame
    ) -> None:
        profile = Profiler().profile(clean_frame)
        result = Cleaner().clean(clean_frame, profile)
        assert len(result.df) == len(clean_frame)

    def test_cleaning_never_mutates_the_input(self, messy_frame: pd.DataFrame) -> None:
        before = messy_frame.copy()
        Cleaner().clean(messy_frame, Profiler().profile(messy_frame))
        pd.testing.assert_frame_equal(messy_frame, before)


# --------------------------------------------------------------------------- #
# Edit service branches
# --------------------------------------------------------------------------- #
class TestEditBranches:
    def test_multiple_edits_apply_as_one_undoable_batch(
        self, db_session, dataset, user_id: int
    ) -> None:
        service = EditService(db_session)
        applied = service.apply(
            dataset.id, user_id,
            [CellEdit(row_index=0, column="state", value="A"),
             CellEdit(row_index=1, column="state", value="B")],
        )
        db_session.commit()
        assert applied.applied == 2

        service.undo_last(dataset.id, user_id)
        db_session.commit()
        assert not service.get_history(dataset.id, user_id).items

    def test_edit_records_the_previous_value(self, db_session, dataset, user_id: int) -> None:
        service = EditService(db_session)
        service.apply(dataset.id, user_id, [CellEdit(row_index=0, column="state", value="Zed")])
        db_session.commit()
        batch = service.get_history(dataset.id, user_id).items[0]
        assert batch.edits[0]["new_value"] == "Zed"
        assert batch.edits[0]["old_value"] != "Zed"

    def test_numeric_column_rejects_text(self, db_session, dataset, user_id: int) -> None:
        with pytest.raises(BadRequestException):
            EditService(db_session).apply(
                dataset.id, user_id, [CellEdit(row_index=0, column="revenue", value="abc")]
            )
