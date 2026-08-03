"""Dashboard tab: chart building and the human-in-the-loop command flow.

Covers ``core/engines/chart_recommender.py`` and the planning/validation half
of ``services/dashboard_service.py`` — the guards that stop a plausible-looking
but wrong widget reaching the dashboard.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.core.engines.chart_recommender import ChartRecommender, parse_dates
from app.core.engines.profiler import Profiler
from app.services.dashboard_service import DashboardService


@pytest.fixture
def recommender() -> ChartRecommender:
    return ChartRecommender()


@pytest.fixture
def sales_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "region": ["North", "South", "North", "East", None],
            "product": ["A", "B", "A", "C", "A"],
            "revenue": [10.0, 20.0, 30.0, None, 50.0],
            "units": [1, 2, 3, 4, 5],
            "sold_on": ["2024-01-05", "15/02/2024", "2024/03/20", "not a date", "2024-04-05"],
        }
    )


# --------------------------------------------------------------------------- #
# Date parsing
# --------------------------------------------------------------------------- #
class TestParseDates:
    def test_recovers_mixed_formats_in_one_column(self) -> None:
        series = pd.Series(["15/02/2024", "2024-04-10", "2024/03/20", "not a date"])
        parsed = parse_dates(series)
        assert parsed.notna().sum() == 3

    def test_keeps_distinct_months_rather_than_collapsing(self) -> None:
        """Regression: a single to_datetime call put every row in one month."""
        series = pd.Series(["15/02/2024", "2024-04-10", "2024/03/20"])
        assert parse_dates(series).dt.to_period("M").nunique() == 3

    def test_passes_through_real_datetimes(self) -> None:
        series = pd.to_datetime(pd.Series(["2024-01-01", "2024-02-01"]))
        assert parse_dates(series).equals(series)

    def test_all_junk_yields_all_nat(self) -> None:
        assert parse_dates(pd.Series(["x", "y"])).isna().all()


# --------------------------------------------------------------------------- #
# Chart building + coverage reporting
# --------------------------------------------------------------------------- #
class TestChartBuilders:
    def test_category_chart_reports_excluded_rows_per_column(
        self, recommender: ChartRecommender, sales_frame: pd.DataFrame
    ) -> None:
        chart = recommender._category_chart(sales_frame, "region", "revenue")
        notes = " ".join(chart["meta"]["notes"])
        assert "region" in notes and "revenue" in notes
        assert chart["meta"]["rows_total"] == len(sales_frame)

    def test_single_category_chart_warns_it_is_uninformative(
        self, recommender: ChartRecommender
    ) -> None:
        frame = pd.DataFrame({"c": ["only", "only"], "v": [1.0, 2.0]})
        chart = recommender._category_chart(frame, "c", "v")
        assert any("only one distinct value" in n for n in chart["meta"]["notes"])

    def test_high_cardinality_rolls_the_tail_into_other(
        self, recommender: ChartRecommender
    ) -> None:
        size = ChartRecommender.MAX_CATEGORIES + 30
        frame = pd.DataFrame({"c": [f"c{i}" for i in range(size)], "v": [1.0] * size})
        chart = recommender._category_chart(frame, "c", "v")
        assert len(chart["data"]) == ChartRecommender.MAX_CATEGORIES + 1
        assert chart["data"][-1]["name"] == ChartRecommender.OTHER_LABEL
        assert any("grouped as" in n for n in chart["meta"]["notes"])

    def test_other_bucket_preserves_the_true_total(self, recommender: ChartRecommender) -> None:
        size = ChartRecommender.MAX_CATEGORIES + 10
        frame = pd.DataFrame({"c": [f"c{i}" for i in range(size)], "v": [2.0] * size})
        chart = recommender._category_chart(frame, "c", "v")
        assert sum(point["value"] for point in chart["data"]) == pytest.approx(2.0 * size)

    def test_line_chart_uses_robust_date_parsing(
        self, recommender: ChartRecommender, sales_frame: pd.DataFrame
    ) -> None:
        chart = recommender._line_chart(sales_frame, "sold_on", "revenue")
        assert chart["type"] == "line"
        assert len(chart["data"]) >= 2, "mixed formats must not collapse to one point"

    def test_line_chart_warns_when_it_collapses_to_one_point(
        self, recommender: ChartRecommender
    ) -> None:
        frame = pd.DataFrame({"d": ["2024-01-05", "2024-01-06"], "v": [1.0, 2.0]})
        chart = recommender._line_chart(frame, "d", "v")
        assert any("single month" in n for n in chart["meta"]["notes"])

    def test_scatter_samples_across_the_whole_frame(self, recommender: ChartRecommender) -> None:
        size = ChartRecommender.MAX_SCATTER_POINTS * 2
        frame = pd.DataFrame({"x": range(size), "y": range(size)}).sort_values("x")
        chart = recommender._scatter_chart(frame, "x", "y")
        xs = [point["x"] for point in chart["data"]]
        assert max(xs) > size * 0.9, "sampling must span the range, not take the head"
        assert any("evenly spaced" in n for n in chart["meta"]["notes"])

    def test_distribution_chart_bins_numeric_values(
        self, recommender: ChartRecommender
    ) -> None:
        frame = pd.DataFrame({"v": [float(i) for i in range(100)]})
        chart = recommender._distribution_chart(frame, "v")
        assert chart["type"] == "bar"
        assert 2 <= len(chart["data"]) <= 10

    def test_coverage_never_exceeds_the_row_total(
        self, recommender: ChartRecommender, sales_frame: pd.DataFrame
    ) -> None:
        for chart in (
            recommender._category_chart(sales_frame, "region", "revenue"),
            recommender._line_chart(sales_frame, "sold_on", "revenue"),
            recommender._scatter_chart(sales_frame, "revenue", "units"),
            recommender._distribution_chart(sales_frame, "revenue"),
        ):
            meta = chart["meta"]
            assert 0 <= meta["rows_used"] <= meta["rows_total"]

    def test_axis_labels_state_the_aggregation(
        self, recommender: ChartRecommender, sales_frame: pd.DataFrame
    ) -> None:
        """"revenue by product" must not leave the reader guessing sum vs avg."""
        chart = recommender._category_chart(sales_frame, "region", "revenue")
        assert chart["x_label"] == "region"
        assert chart["y_label"] == "Total revenue"
        assert chart["title"] == "Total revenue by region"

    @pytest.fixture
    def grouped_frame(self) -> pd.DataFrame:
        return pd.DataFrame({
            "state": ["CA", "CA", "NY", "NY", "TX"],
            "revenue": [100.0, 300.0, 50.0, 150.0, 80.0],
            "sold_on": ["2024-01-05", "2024-02-05", "2024-01-10", "2024-03-01", "2024-02-20"],
        })

    @pytest.mark.parametrize(
        ("measure_token", "word", "expected"),
        [
            ("revenue", "Total", [400.0, 200.0, 80.0]),
            ("avg(revenue)", "Average", [200.0, 100.0, 80.0]),
            ("max(revenue)", "Maximum", [300.0, 150.0, 80.0]),
            ("min(revenue)", "Minimum", [100.0, 80.0, 50.0]),
        ],
    )
    def test_chart_honours_the_requested_aggregation(
        self, recommender: ChartRecommender, grouped_frame: pd.DataFrame,
        measure_token: str, word: str, expected: list[float],
    ) -> None:
        """Regression: "average revenue by state" used to chart totals."""
        profile = Profiler().profile(grouped_frame)
        chart = recommender.materialize_chart(
            grouped_frame, profile, f"chart:bar:state:{measure_token}"
        )
        assert chart is not None
        assert chart["title"] == f"{word} revenue by state"
        assert chart["y_label"] == f"{word} revenue"
        assert sorted([p["value"] for p in chart["data"]], reverse=True) == sorted(expected, reverse=True)

    @pytest.mark.parametrize("agg", sorted(ChartRecommender.AGGREGATIONS))
    def test_every_aggregation_works_on_both_kpi_and_chart(
        self, recommender: ChartRecommender, grouped_frame: pd.DataFrame, agg: str
    ) -> None:
        """Regression: "median revenue" was refused on the KPI path only.

        The two paths shared no list, so an aggregation could be chartable and
        un-KPI-able at the same time.
        """
        profile = Profiler().profile(grouped_frame)
        kpi = recommender.materialize_kpi(grouped_frame, profile, f"kpi:{agg}:revenue")
        assert kpi is not None, f"KPI refused {agg}"
        assert kpi["label"] and kpi["value"] is not None

        chart = recommender.materialize_chart(
            grouped_frame, profile, f"chart:bar:state:{agg}(revenue)"
        )
        assert chart is not None, f"chart refused {agg}"
        assert "revenue" in chart["y_label"]

    def test_no_aggregation_ever_emits_a_non_finite_value(
        self, recommender: ChartRecommender
    ) -> None:
        """NaN is not valid JSON and renders as a silent gap."""
        import math

        # TX has a single row, so its spread is undefined.
        frame = pd.DataFrame({
            "state": ["CA", "CA", "TX"],
            "revenue": [10.0, 20.0, 80.0],
        })
        profile = Profiler().profile(frame)
        for agg in ("stddev", "variance"):
            chart = recommender.materialize_chart(frame, profile, f"chart:bar:state:{agg}(revenue)")
            assert chart is not None
            values = [p["value"] for p in chart["data"]]
            assert all(math.isfinite(v) for v in values), f"{agg} leaked a non-finite value"
            assert any("too few rows" in n for n in chart["meta"]["notes"])

    def test_captions_read_as_english(
        self, recommender: ChartRecommender, grouped_frame: pd.DataFrame
    ) -> None:
        profile = Profiler().profile(grouped_frame)
        expected = {
            "sum": "Total revenue",
            "avg": "Average revenue",
            "median": "Median revenue",
            "stddev": "Std deviation of revenue",
            "count_distinct": "Distinct revenue values",
        }
        for agg, caption in expected.items():
            chart = recommender.materialize_chart(
                grouped_frame, profile, f"chart:bar:state:{agg}(revenue)"
            )
            assert chart["y_label"] == caption

    def test_line_chart_honours_the_requested_aggregation(
        self, recommender: ChartRecommender, grouped_frame: pd.DataFrame
    ) -> None:
        profile = Profiler().profile(grouped_frame)
        chart = recommender.materialize_chart(
            grouped_frame, profile, "chart:line:sold_on:avg(revenue)"
        )
        assert chart is not None
        assert chart["y_label"] == "Average revenue"
        assert chart["data"][0]["value"] == pytest.approx(75.0)

    def test_a_bare_measure_still_means_sum(self, recommender: ChartRecommender) -> None:
        """Chart ids saved before aggregations existed must keep working."""
        assert ChartRecommender._parse_measure("revenue") == ("sum", "revenue")
        assert ChartRecommender._parse_measure("avg(revenue)") == ("avg", "revenue")
        assert ChartRecommender._parse_measure("bogus(revenue)") == ("sum", "bogus(revenue)")

    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            ("average revenue by state", "avg"),
            ("mean revenue by state", "avg"),
            ("total revenue by state", None),
            ("revenue by state", None),
            ("largest revenue by state", "max"),
            ("smallest revenue by state", "min"),
        ],
    )
    def test_requested_aggregation_is_read_from_the_wording(
        self, command: str, expected: str | None
    ) -> None:
        assert DashboardService._requested_agg(command) == expected

    def test_non_sum_charts_do_not_get_an_other_bucket(
        self, recommender: ChartRecommender
    ) -> None:
        """Summing averages into "Other" would be meaningless."""
        size = ChartRecommender.MAX_CATEGORIES + 5
        frame = pd.DataFrame({"c": [f"c{i}" for i in range(size)], "v": [2.0] * size})
        chart = recommender._category_chart(frame, "c", "v", agg="avg")
        assert all(point["name"] != ChartRecommender.OTHER_LABEL for point in chart["data"])
        assert len(chart["data"]) == ChartRecommender.MAX_CATEGORIES

    def test_count_chart_labels_the_y_axis_as_rows(
        self, recommender: ChartRecommender, sales_frame: pd.DataFrame
    ) -> None:
        chart = recommender._category_chart(sales_frame, "region", None)
        assert chart["y_label"] == "Number of rows"

    def test_line_chart_labels_the_time_axis(
        self, recommender: ChartRecommender, sales_frame: pd.DataFrame
    ) -> None:
        chart = recommender._line_chart(sales_frame, "sold_on", "revenue")
        assert chart["x_label"] == "Month"
        assert chart["y_label"] == "Total revenue"

    def test_scatter_labels_both_columns(
        self, recommender: ChartRecommender, sales_frame: pd.DataFrame
    ) -> None:
        chart = recommender._scatter_chart(sales_frame, "revenue", "units")
        assert chart["x_label"] == "revenue"
        assert chart["y_label"] == "units"

    def test_distribution_labels_bins_and_row_counts(
        self, recommender: ChartRecommender, sales_frame: pd.DataFrame
    ) -> None:
        chart = recommender._distribution_chart(sales_frame, "revenue")
        assert chart["x_label"] == "revenue range"
        assert chart["y_label"] == "Number of rows"

    def test_every_builder_supplies_both_axis_labels(
        self, recommender: ChartRecommender, sales_frame: pd.DataFrame
    ) -> None:
        for chart in (
            recommender._category_chart(sales_frame, "region", "revenue"),
            recommender._line_chart(sales_frame, "sold_on", "revenue"),
            recommender._scatter_chart(sales_frame, "revenue", "units"),
            recommender._distribution_chart(sales_frame, "revenue"),
        ):
            assert chart["x_label"] and chart["y_label"], chart["title"]

    def test_missing_breakdown_names_only_guilty_columns(
        self, recommender: ChartRecommender
    ) -> None:
        text = recommender._missing_breakdown({"good": 0, "bad": 7})
        assert "bad" in text and "good" not in text


# --------------------------------------------------------------------------- #
# Command planning guards (pure functions — no DB, no LLM)
# --------------------------------------------------------------------------- #
class TestCommandGuards:
    @pytest.fixture
    def profile(self, sales_frame: pd.DataFrame):
        return Profiler().profile(sales_frame)

    def test_named_columns_tolerates_spaces_for_underscores(self, profile) -> None:
        frame = pd.DataFrame({"PROP_CLASS": ["a"], "SALE_PRICE": [1.0]})
        prof = Profiler().profile(frame)
        names = {c.name for c in DashboardService._named_columns("avg sale price by prop class", prof)}
        assert names == {"PROP_CLASS", "SALE_PRICE"}

    def test_named_columns_empty_when_nothing_matches(self, profile) -> None:
        assert DashboardService._named_columns("profit margin by warehouse", profile) == []

    def test_plan_uses_rejects_a_chart_that_drops_a_named_column(self, profile) -> None:
        named = DashboardService._named_columns("units vs revenue", profile)
        plan = {"kind": "chart", "type": "bar", "x": "product", "y": "revenue"}
        assert DashboardService._plan_uses(plan, named) is False

    def test_plan_uses_allows_extra_columns_a_chart_needs(self, profile) -> None:
        named = DashboardService._named_columns("revenue over time", profile)
        plan = {"kind": "chart", "type": "line", "x": "sold_on", "y": "revenue"}
        assert DashboardService._plan_uses(plan, named) is True

    def test_plan_uses_lets_a_kpi_ignore_the_grouping_column(self, profile) -> None:
        named = DashboardService._named_columns("average revenue by region", profile)
        assert DashboardService._plan_uses({"kind": "kpi", "column": "revenue"}, named) is True

    @pytest.mark.parametrize(
        ("plan", "valid"),
        [
            ({"kind": "chart", "type": "line", "x": "sold_on", "y": "revenue"}, True),
            ({"kind": "chart", "type": "line", "x": "revenue", "y": "units"}, False),
            ({"kind": "chart", "type": "scatter", "x": "revenue", "y": "units"}, True),
            ({"kind": "chart", "type": "scatter", "x": "region", "y": "revenue"}, False),
            ({"kind": "chart", "type": "scatter", "x": "revenue", "y": "revenue"}, False),
            ({"kind": "chart", "type": "hist", "x": "revenue", "y": None}, True),
            ({"kind": "chart", "type": "hist", "x": "region", "y": None}, False),
            ({"kind": "chart", "type": "bar", "x": "region", "y": "count"}, True),
            ({"kind": "chart", "type": "bar", "x": "region", "y": "product"}, False),
            ({"kind": "kpi", "agg": "avg", "column": "revenue"}, True),
        ],
    )
    def test_plan_fits_types_matches_column_semantics(self, profile, plan, valid) -> None:
        assert DashboardService._plan_fits_types(plan, profile) is valid

    def test_line_without_a_date_axis_is_rejected(self, profile) -> None:
        """Regression: a line over two numerics parsed a number as a date."""
        plan = {"kind": "chart", "type": "line", "x": "revenue", "y": "units"}
        assert DashboardService._plan_fits_types(plan, profile) is False

    def test_explicit_vs_wording_forces_a_scatter(self, profile) -> None:
        named = DashboardService._named_columns("revenue vs units", profile)
        plan = DashboardService._explicit_intent("revenue vs units", named)
        assert plan and plan["type"] == "scatter"

    def test_explicit_distribution_wording_forces_a_histogram(self, profile) -> None:
        named = DashboardService._named_columns("distribution of revenue", profile)
        plan = DashboardService._explicit_intent("distribution of revenue", named)
        assert plan and plan["type"] == "hist"

    def test_explicit_intent_declines_when_columns_cannot_support_it(self, profile) -> None:
        named = DashboardService._named_columns("region vs product", profile)
        assert DashboardService._explicit_intent("region vs product", named) is None

    def test_inferred_note_names_columns_the_user_never_typed(self, profile) -> None:
        named = DashboardService._named_columns("average revenue", profile)
        note = DashboardService._inferred_note({"kind": "kpi", "column": "units"}, named)
        assert note and "units" in note

    def test_inferred_note_is_silent_when_everything_was_named(self, profile) -> None:
        named = DashboardService._named_columns("average revenue", profile)
        assert DashboardService._inferred_note({"kind": "kpi", "column": "revenue"}, named) is None

    def test_count_is_not_treated_as_an_inferred_column(self, profile) -> None:
        named = DashboardService._named_columns("count by region", profile)
        plan = {"kind": "chart", "type": "bar", "x": "region", "y": "count"}
        assert DashboardService._inferred_note(plan, named) is None

    def test_ungrouped_note_fires_when_the_grouping_is_unrecognised(self, profile) -> None:
        named = DashboardService._named_columns("average revenue by pro class", profile)
        note = DashboardService._ungrouped_note(
            "average revenue by pro class", named, {"kind": "kpi", "column": "revenue"}
        )
        assert note and "grouping column" in note

    def test_ungrouped_note_is_silent_without_a_grouping_request(self, profile) -> None:
        named = DashboardService._named_columns("average revenue", profile)
        assert DashboardService._ungrouped_note(
            "average revenue", named, {"kind": "kpi", "column": "revenue"}
        ) is None

    def test_ungrouped_note_is_silent_when_the_grouping_resolved(self, profile) -> None:
        named = DashboardService._named_columns("average revenue by region", profile)
        assert DashboardService._ungrouped_note(
            "average revenue by region", named, {"kind": "kpi", "column": "revenue"}
        ) is None

    def test_examples_are_built_from_this_dataset_s_own_columns(self, profile) -> None:
        examples = DashboardService._example_commands(profile)
        assert "revenue" in examples or "units" in examples

    def test_unbuildable_message_names_what_was_recognised(self, profile) -> None:
        named = DashboardService._named_columns("total revenue by region", profile)
        message = DashboardService._unbuildable_message(named, profile)
        assert "revenue" in message or "region" in message
