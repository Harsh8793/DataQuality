"""Chat tab: SQL safety, answer grounding and the anti-wrong-answer guards.

Covers ``core/engines/duckdb_engine.py`` and ``agents/chat_agent.py``. Each
guard here exists because the tab produced a confidently worded wrong answer
without it, so the tests are written as regressions against those answers.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.agents.base import AgentContext
from app.agents.chat_agent import ChatAgent
from app.core.engines.duckdb_engine import DuckDBEngine, QueryResult
from app.core.engines.profiler import Profiler
from app.exceptions.base import BadRequestException


@pytest.fixture
def engine() -> DuckDBEngine:
    return DuckDBEngine()


@pytest.fixture
def agent() -> ChatAgent:
    return ChatAgent()


@pytest.fixture
def ctx(messy_frame: pd.DataFrame) -> AgentContext:
    context = AgentContext(dataset_id=1, dataset_name="messy", df=messy_frame)
    context.profile = Profiler().profile(messy_frame)
    return context


def result_of(columns: list[str], rows: list[dict], sql: str = "SELECT 1 LIMIT 10") -> QueryResult:
    return QueryResult(columns=columns, rows=rows, row_count=len(rows), sql=sql)


# --------------------------------------------------------------------------- #
# SQL safety
# --------------------------------------------------------------------------- #
class TestDuckDBValidation:
    @pytest.mark.parametrize(
        "sql",
        [
            "DROP TABLE dataset",
            "DELETE FROM dataset",
            "UPDATE dataset SET a = 1",
            "INSERT INTO dataset VALUES (1)",
            "CREATE TABLE x (a INT)",
            "ALTER TABLE dataset ADD COLUMN b INT",
        ],
    )
    def test_rejects_write_statements(self, engine: DuckDBEngine, sql: str) -> None:
        with pytest.raises(BadRequestException):
            engine.validate(sql)

    def test_rejects_stacked_statements(self, engine: DuckDBEngine) -> None:
        with pytest.raises(BadRequestException, match="Multiple"):
            engine.validate("SELECT 1; SELECT 2")

    def test_rejects_empty_sql(self, engine: DuckDBEngine) -> None:
        with pytest.raises(BadRequestException, match="Empty"):
            engine.validate("   ")

    def test_allows_select_and_cte(self, engine: DuckDBEngine) -> None:
        assert "SELECT" in engine.validate("SELECT * FROM dataset")
        assert engine.validate("WITH t AS (SELECT 1) SELECT * FROM t")

    def test_injects_a_limit_when_missing(self, engine: DuckDBEngine) -> None:
        assert f"LIMIT {DuckDBEngine.MAX_ROWS}" in engine.validate("SELECT * FROM dataset")

    def test_keeps_an_existing_limit(self, engine: DuckDBEngine) -> None:
        assert engine.validate("SELECT * FROM dataset LIMIT 5").endswith("LIMIT 5")

    def test_trailing_semicolon_is_tolerated(self, engine: DuckDBEngine) -> None:
        assert engine.validate("SELECT 1;")


class TestDuckDBExecution:
    def test_runs_aggregate_against_the_frame(
        self, engine: DuckDBEngine, clean_frame: pd.DataFrame
    ) -> None:
        result = engine.execute(clean_frame, "SELECT SUM(sales) AS total FROM dataset")
        assert result.rows[0]["total"] == pytest.approx(100.0)

    def test_caps_returned_rows(self, engine: DuckDBEngine) -> None:
        frame = pd.DataFrame({"a": range(DuckDBEngine.MAX_ROWS + 500)})
        result = engine.execute(frame, "SELECT * FROM dataset")
        assert result.row_count <= DuckDBEngine.MAX_ROWS

    def test_nan_becomes_null_not_a_float(
        self, engine: DuckDBEngine
    ) -> None:
        frame = pd.DataFrame({"a": [1.0, None]})
        result = engine.execute(frame, "SELECT * FROM dataset")
        assert result.rows[1]["a"] is None

    def test_datetime_columns_serialize_as_strings(self, engine: DuckDBEngine) -> None:
        """Regression: Timestamp is not JSON serializable and 500'd the API."""
        frame = pd.DataFrame({"d": pd.to_datetime(["2024-01-05", "2024-02-06"])})
        result = engine.execute(frame, "SELECT * FROM dataset")
        assert all(isinstance(row["d"], str) for row in result.rows)
        assert result.rows[0]["d"] == "2024-01-05"

    def test_invalid_sql_raises_a_readable_error(
        self, engine: DuckDBEngine, clean_frame: pd.DataFrame
    ) -> None:
        with pytest.raises(BadRequestException, match="SQL execution failed"):
            engine.execute(clean_frame, "SELECT nope FROM dataset")


# --------------------------------------------------------------------------- #
# Number grounding
# --------------------------------------------------------------------------- #
class TestNumberGrounding:
    def test_accepts_rounded_restatement_of_a_single_value(self, agent: ChatAgent) -> None:
        assert agent._numbers_agree("about $3,954", [3953.85]) is True

    def test_rejects_a_fabricated_single_value(self, agent: ChatAgent) -> None:
        assert agent._numbers_agree("about $1,791", [3953.85]) is False

    def test_accepts_text_without_numbers_when_truth_is_empty(self, agent: ChatAgent) -> None:
        assert agent._numbers_agree("no numeric result", []) is True

    def test_rejects_text_with_no_numbers_when_a_value_exists(self, agent: ChatAgent) -> None:
        assert agent._numbers_agree("some prose", [42.0]) is False

    @pytest.mark.parametrize(
        ("text", "accepted"),
        [
            ("$7,945.76", True),    # exact to the cent
            ("$7,946", True),       # rounded to a whole unit
            ("$7,945.8", True),     # rounded to one decimal
            ("$7,946.16", False),   # regression: altered cents, within 2%
            ("$7,900", False),      # too coarse to be a rounding
            ("$1,791", False),      # fabricated
        ],
    )
    def test_only_faithful_roundings_are_accepted(
        self, agent: ChatAgent, text: str, accepted: bool
    ) -> None:
        """A percentage tolerance let "7,946.16" pass for 7,945.7618.

        It states different cents, so it reads as a precise figure the data
        never produced — the check now rounds to the precision claimed.
        """
        assert agent._numbers_agree(text, [7945.761805555559]) is accepted

    def test_rounding_is_allowed_but_altered_cents_are_not(self, agent: ChatAgent) -> None:
        assert agent._numbers_agree("about $3,954", [3953.85]) is True
        assert agent._numbers_agree("about $3,954.12", [3953.85]) is False

    def test_multi_row_guard_also_rejects_altered_cents(self, agent: ChatAgent) -> None:
        rows = [{"state": "NY", "avg_revenue": 7945.761805555559}]
        result = result_of(["state", "avg_revenue"], rows + [{"state": "CA", "avg_revenue": 10048.8}])
        assert agent._numbers_are_grounded("New York averages $7,945.76", result) is True
        assert agent._numbers_are_grounded("New York averages $7,946.16", result) is False

    def test_zero_is_matched_exactly(self, agent: ChatAgent) -> None:
        assert agent._numbers_agree("there are 0 rows", [0.0]) is True
        assert agent._numbers_agree("there are 5 rows", [0.0]) is False

    def test_multi_row_answer_may_cite_the_row_count(self, agent: ChatAgent) -> None:
        """Regression: the model reported the 10-row preview as the total."""
        result = result_of(["name"], [{"name": f"n{i}"} for i in range(87)])
        assert agent._numbers_are_grounded("There are 87 customers.", result) is True

    def test_multi_row_answer_cannot_invent_a_count(self, agent: ChatAgent) -> None:
        result = result_of(["name"], [{"name": f"n{i}"} for i in range(87)])
        assert agent._numbers_are_grounded("There are 4 customers.", result) is False

    def test_values_present_in_rows_are_allowed(self, agent: ChatAgent) -> None:
        result = result_of(["state", "total"], [{"state": "CA", "total": 753660.34}])
        assert agent._numbers_are_grounded("California totals 753,660.34", result) is True

    def test_prose_without_numbers_is_allowed(self, agent: ChatAgent) -> None:
        result = result_of(["a"], [{"a": 1}, {"a": 2}])
        assert agent._numbers_are_grounded("Several rows were returned.", result) is True


# --------------------------------------------------------------------------- #
# Filter normalisation and caveats
# --------------------------------------------------------------------------- #
class TestFilterHandling:
    def test_rewrites_unquoted_equality_case_insensitively(self, agent: ChatAgent) -> None:
        sql = agent._normalize_text_filters(
            "SELECT COUNT(*) FROM dataset WHERE gender = 'M'", {"gender"}
        )
        assert "LOWER(TRIM(CAST(\"gender\" AS VARCHAR))) = 'm'" in sql

    def test_rewrites_quoted_column_names(self, agent: ChatAgent) -> None:
        sql = agent._normalize_text_filters(
            "SELECT * FROM dataset WHERE \"state\" = 'California'", {"state"}
        )
        assert "'california'" in sql

    def test_rewrites_column_names_containing_spaces(self, agent: ChatAgent) -> None:
        sql = agent._normalize_text_filters(
            "SELECT * FROM dataset WHERE \"Full Name\" = 'Ann'", {"Full Name"}
        )
        assert '"Full Name"' in sql and "'ann'" in sql

    def test_leaves_numeric_comparisons_alone(self, agent: ChatAgent) -> None:
        sql = "SELECT * FROM dataset WHERE quantity = 5"
        assert agent._normalize_text_filters(sql, {"gender"}) == sql

    def test_leaves_unknown_columns_alone(self, agent: ChatAgent) -> None:
        sql = "SELECT * FROM dataset WHERE mystery = 'x'"
        assert agent._normalize_text_filters(sql, {"gender"}) == sql

    def test_rewrites_every_filter_in_a_multi_predicate_query(self, agent: ChatAgent) -> None:
        sql = agent._normalize_text_filters(
            "SELECT * FROM dataset WHERE state = 'Texas' AND product = 'Laptop'",
            {"state", "product"},
        )
        assert sql.count("LOWER(TRIM(") == 2

    def test_extracts_filters_before_rewriting(self, agent: ChatAgent) -> None:
        pairs = agent._equality_filters(
            "SELECT * FROM dataset WHERE gender = 'M'", {"gender"}
        )
        assert pairs == [("gender", "m")]

    def test_variant_caveat_warns_about_abbreviated_spellings(
        self, agent: ChatAgent, messy_frame: pd.DataFrame
    ) -> None:
        """'m' and 'male' may be the same category — say so, don't merge silently."""
        notes = agent._variant_caveats(messy_frame, [("gender", "m")])
        assert notes and "male" in notes[0]

    def test_variant_caveat_silent_for_an_unambiguous_value(
        self, agent: ChatAgent, messy_frame: pd.DataFrame
    ) -> None:
        assert agent._variant_caveats(messy_frame, [("product", "webcam")]) == []

    def test_variant_caveat_ignores_unknown_columns(
        self, agent: ChatAgent, messy_frame: pd.DataFrame
    ) -> None:
        assert agent._variant_caveats(messy_frame, [("nope", "x")]) == []


# --------------------------------------------------------------------------- #
# Aggregate intent
# --------------------------------------------------------------------------- #
class TestAggregateIntent:
    @pytest.mark.parametrize(
        ("question", "sql", "expected"),
        [
            ("what is the average revenue", "SELECT SUM(revenue) AS avg_revenue FROM t", "AVG"),
            ("what is the total revenue", "SELECT AVG(revenue) FROM t", "SUM"),
            ("average revenue", "SELECT AVG(revenue) FROM t", None),
            ("how many rows", "SELECT COUNT(*) FROM t", None),
            ("show min max and average", "SELECT MIN(a), MAX(a), AVG(a) FROM t", None),
            ("what colour is it", "SELECT AVG(a) FROM t", None),
        ],
    )
    def test_detects_only_genuine_mismatches(
        self, agent: ChatAgent, question: str, sql: str, expected: str | None
    ) -> None:
        assert agent._aggregate_mismatch(question, sql) == expected


# --------------------------------------------------------------------------- #
# Dropped filters, caveats and date normalisation
# --------------------------------------------------------------------------- #
class TestAnswerCaveats:
    def test_flags_a_value_that_never_reached_the_sql(
        self, agent: ChatAgent, ctx: AgentContext
    ) -> None:
        note = agent._dropped_filter_note(ctx, "average revenue for laptops", "SELECT AVG(revenue) FROM dataset")
        assert note and "Laptop" in note

    def test_silent_when_the_filter_is_present(self, agent: ChatAgent, ctx: AgentContext) -> None:
        sql = "SELECT AVG(revenue) FROM dataset WHERE product = 'Laptop'"
        assert agent._dropped_filter_note(ctx, "average revenue for laptops", sql) is None

    def test_silent_when_no_value_was_named(self, agent: ChatAgent, ctx: AgentContext) -> None:
        assert agent._dropped_filter_note(ctx, "average revenue", "SELECT AVG(revenue) FROM dataset") is None

    def test_plural_wording_still_matches_a_singular_value(
        self, agent: ChatAgent, ctx: AgentContext
    ) -> None:
        found = agent._filter_clause(ctx, "average revenue for laptops")
        assert found == ("product", "Laptop")

    def test_query_frame_parses_mixed_dates_and_reports_junk(
        self, agent: ChatAgent, ctx: AgentContext
    ) -> None:
        frame, notes = agent._query_frame(ctx)
        assert pd.api.types.is_datetime64_any_dtype(frame["order_date"])
        assert any("order_date" in note for note in notes)

    def test_query_frame_is_a_copy(self, agent: ChatAgent, ctx: AgentContext) -> None:
        frame, _ = agent._query_frame(ctx)
        assert frame is not ctx.df
        assert not pd.api.types.is_datetime64_any_dtype(ctx.df["order_date"])

    def test_note_applies_only_to_columns_in_the_query(self, agent: ChatAgent) -> None:
        note = "12 of 100 'order_date' values aren't recognisable dates"
        assert agent._note_applies(note, "SELECT * FROM t WHERE order_date > '2024'") is True
        assert agent._note_applies(note, "SELECT AVG(revenue) FROM t") is False

    def test_truncation_is_disclosed(self, agent: ChatAgent) -> None:
        result = result_of(["a"], [{"a": i} for i in range(50)], sql="SELECT * FROM t LIMIT 50")
        assert any("limited to" in note for note in agent._result_caveats(result))

    def test_deliberate_top_n_is_not_called_truncation(self, agent: ChatAgent) -> None:
        result = result_of(["a"], [{"a": 1}], sql="SELECT a FROM t ORDER BY a DESC LIMIT 1")
        assert agent._result_caveats(result) == []


# --------------------------------------------------------------------------- #
# Deterministic narration
# --------------------------------------------------------------------------- #
class TestDeterministicNarration:
    def test_states_a_single_value_exactly(self, agent: ChatAgent) -> None:
        text = agent._narrate_exact(result_of(["avg_revenue"], [{"avg_revenue": 6330.36}]))
        assert "6,330.36" in text

    def test_humanizes_duckdb_count_star(self, agent: ChatAgent) -> None:
        """Regression: the answer read "The count star() is 42"."""
        text = agent._narrate_exact(result_of(["count_star()"], [{"count_star()": 42}]))
        assert "star" not in text
        assert "42" in text

    def test_reads_out_multiple_summary_values(self, agent: ChatAgent) -> None:
        text = agent._narrate_exact(result_of(["min", "max"], [{"min": 1, "max": 9}]))
        assert "1" in text and "9" in text

    def test_fallback_calls_out_extremes_for_grouped_results(self, agent: ChatAgent) -> None:
        rows = [{"state": "CA", "total": 100.0}, {"state": "NY", "total": 20.0}]
        text = agent._fallback_narrate(result_of(["state", "total"], rows))
        assert "CA" in text and "NY" in text

    def test_fallback_reports_the_true_row_count(self, agent: ChatAgent) -> None:
        rows = [{"name": f"n{i}"} for i in range(500)]
        text = agent._fallback_narrate(result_of(["name"], rows))
        assert "500" in text

    def test_zero_rows_is_stated_plainly(self, agent: ChatAgent) -> None:
        assert "No matching records" in agent._narrate("q", result_of(["a"], []))


# --------------------------------------------------------------------------- #
# Routing helpers
# --------------------------------------------------------------------------- #
class TestRouting:
    @pytest.mark.parametrize(
        "question",
        ["how many rows are there?", "how many records?", "number of rows in this dataset"],
    )
    def test_rowcount_questions_are_recognised(self, agent: ChatAgent, question: str) -> None:
        assert agent._is_rowcount_question(question) is True

    def test_a_column_question_is_not_a_rowcount_question(self, agent: ChatAgent) -> None:
        assert agent._is_rowcount_question("how many rows have missing revenue?") is False

    @pytest.mark.parametrize(
        "answer",
        ["Please run a SQL query to find out.", "I don't have access to the data."],
    )
    def test_deflections_are_detected(self, agent: ChatAgent, answer: str) -> None:
        assert agent._is_deflection(answer) is True

    def test_a_real_answer_is_not_a_deflection(self, agent: ChatAgent) -> None:
        assert agent._is_deflection("The average revenue is $6,330.") is False

    def test_chart_is_offered_for_two_column_results(self, agent: ChatAgent) -> None:
        rows = [{"region": "N", "total": 10.0}, {"region": "S", "total": 20.0}]
        assert agent._maybe_chart(result_of(["region", "total"], rows)) is not None

    def test_no_chart_for_a_single_column_result(self, agent: ChatAgent) -> None:
        assert agent._maybe_chart(result_of(["a"], [{"a": 1}])) is None

    def test_no_chart_for_an_empty_result(self, agent: ChatAgent) -> None:
        assert agent._maybe_chart(result_of(["a", "b"], [])) is None

    def test_requested_chart_type_is_honoured(self, agent: ChatAgent) -> None:
        rows = [{"region": "N", "total": 10.0}, {"region": "S", "total": 20.0}]
        chart = agent._maybe_chart(result_of(["region", "total"], rows), forced="pie")
        assert chart and chart["type"] == "pie"


class TestAxisLabels:
    """SQL aliases carry the aggregation — the axis must spell it out."""

    @pytest.mark.parametrize(
        ("column", "expected"),
        [
            ("sum_revenue", "Total revenue"),
            ("total_sales", "Total sales"),
            ("avg_revenue", "Average revenue"),
            ("mean_price", "Average price"),
            ("max_amount", "Maximum amount"),
            ("min_amount", "Minimum amount"),
            ("count_star()", "Number of rows"),
            ("count", "Number of rows"),
            ("n", "Number of rows"),
            ("row_count", "Number of rows"),
            ("order_date", "order date"),
            ("revenue", "revenue"),
        ],
    )
    def test_alias_is_humanized(self, agent: ChatAgent, column: str, expected: str) -> None:
        assert agent._axis_label(column) == expected

    def test_chart_carries_labels_and_a_titled_measure(self, agent: ChatAgent) -> None:
        rows = [{"state": "CA", "sum_revenue": 100.0}, {"state": "NY", "sum_revenue": 20.0}]
        chart = agent._maybe_chart(result_of(["state", "sum_revenue"], rows))
        assert chart is not None
        assert chart["x_label"] == "state"
        assert chart["y_label"] == "Total revenue"
        assert chart["title"] == "Total revenue by state"

    def test_scatter_labels_both_axes(self, agent: ChatAgent) -> None:
        rows = [{"units": 1.0, "avg_price": 5.0}, {"units": 2.0, "avg_price": 6.0}]
        chart = agent._maybe_chart(result_of(["units", "avg_price"], rows), forced="scatter")
        assert chart is not None
        assert chart["x_label"] == "units"
        assert chart["y_label"] == "Average price"
