"""Dashboard service: build the widget pool and manage a user's custom layout."""

from __future__ import annotations

import json

import pandas as pd
from sqlalchemy.orm import Session

from app.agents.dashboard_agent import DashboardAgent
from app.agents.profiling_agent import ProfilingAgent
from app.constants.enums import SemanticType
from app.core.engines.chart_recommender import ChartRecommender
from app.core.llm import prompts
from app.core.llm.groq_client import get_llm
from app.exceptions.base import BadRequestException
from app.repositories.report_repository import DashboardRepository
from app.schemas.ai import ChartCommandResponse, WidgetOption
from app.schemas.chat import (
    ChartSpec,
    DashboardBuilderResponse,
    DashboardResponse,
    DashboardSelection,
    KpiCard,
    WidgetPool,
)
from app.services.base import BaseService, DatasetContextMixin

_NUMERIC_TYPES = {SemanticType.NUMERIC, SemanticType.INTEGER, SemanticType.CURRENCY}
_TEMPORAL_TYPES = {SemanticType.DATE, SemanticType.DATETIME}
_CATEGORICAL_TYPES = {SemanticType.CATEGORICAL, SemanticType.TEXT, SemanticType.BOOLEAN}


class DashboardService(BaseService, DatasetContextMixin):
    """Generates the dashboard widget pool and persists the user's selection."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.profiling_agent = ProfilingAgent()
        self.dashboard_agent = DashboardAgent()
        self.recommender = ChartRecommender()
        self.dashboards = DashboardRepository(db)

    def build(self, dataset_id: int, user_id: int) -> DashboardResponse:
        """Return the classic auto-dashboard spec (kept for compatibility)."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        ctx = self._build_context(dataset)
        self.profiling_agent.run(ctx)
        spec = self.dashboard_agent.build(ctx)
        return DashboardResponse.model_validate(spec)

    def get_builder(self, dataset_id: int, user_id: int) -> DashboardBuilderResponse:
        """Return the full widget pool plus the user's saved (or default) selection."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        ctx = self._build_context(dataset)
        self.profiling_agent.run(ctx)
        assert ctx.profile is not None
        pool = self.recommender.build_pool(ctx.df, ctx.profile)

        selection = self._load_selection(dataset_id) or self.recommender.default_selection(pool)
        # Saved ids missing from the pool may be custom NL-created widgets:
        # try materializing them so pinned widgets survive reloads; drop the rest.
        kpi_ids = {k["id"] for k in pool["kpis"]}
        chart_ids = {c["id"] for c in pool["charts"]}
        for kid in selection["kpis"]:
            if kid not in kpi_ids:
                widget = self.recommender.materialize_kpi(ctx.df, ctx.profile, kid)
                if widget is not None:
                    pool["kpis"].append(widget)
                    kpi_ids.add(kid)
        for cid in selection["charts"]:
            if cid not in chart_ids:
                widget = self.recommender.materialize_chart(ctx.df, ctx.profile, cid)
                if widget is not None:
                    pool["charts"].append(widget)
                    chart_ids.add(cid)
        selection = {
            "kpis": [i for i in selection["kpis"] if i in kpi_ids],
            "charts": [i for i in selection["charts"] if i in chart_ids],
        }

        return DashboardBuilderResponse(
            pool=WidgetPool(
                kpis=[KpiCard(**k) for k in pool["kpis"]],
                charts=[ChartSpec(**c) for c in pool["charts"]],
            ),
            selected=DashboardSelection(**selection),
        )

    def save_selection(self, dataset_id: int, user_id: int, kpis: list[str], charts: list[str]) -> None:
        """Persist the user's selected widget ids for this dataset."""
        self._load_owned_dataset(dataset_id, user_id)
        spec = {"kpis": kpis, "charts": charts}
        existing = self.dashboards.latest_for_dataset(dataset_id)
        if existing is not None:
            self.dashboards.update(existing, spec=spec)
        else:
            self.dashboards.create(user_id=user_id, dataset_id=dataset_id, spec=spec, created_by=user_id)
        self.db.commit()

    # ---- NL chart-on-command ------------------------------------------ #
    def command(self, dataset_id: int, user_id: int, command: str) -> ChartCommandResponse:
        """Turn a natural-language request into a KPI or chart widget."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        ctx = self._build_context(dataset)
        self.profiling_agent.run(ctx)
        assert ctx.profile is not None

        named = self._named_columns(command, ctx.profile)
        # The model will happily answer a question about columns you don't have
        # by substituting ones you do. If nothing in the request matches a real
        # column, refuse rather than charting something unrelated.
        if not named:
            examples = self._example_commands(ctx.profile)
            raise BadRequestException(
                "None of your columns are named in that request, so I'd only be guessing. "
                + (f"Try something like: {examples}." if examples else "Try naming a column.")
            )

        # When the user states the chart shape outright, that beats the model's
        # guess — "spend vs units" means a scatter, not a bar of one against
        # the other.
        plan = self._explicit_intent(command, named) or self._plan_command(command, ctx.profile)
        # A plan whose chart type the columns can't support is unusable, so fall
        # back to the keyword planner. A plan that resolved a misspelt column to
        # a real one is *useful* — it goes through as a proposal, with the
        # substitution spelled out for the user to confirm or reject.
        if not self._plan_fits_types(plan, ctx.profile):
            plan = self._heuristic_command(command, ctx.profile)
            if not self._plan_fits_types(plan, ctx.profile):
                plan = None

        if plan is None or plan.get("kind") == "error":
            raise BadRequestException(
                plan.get("message") if plan else self._unbuildable_message(named, ctx.profile)
            )

        # A chart planned straight from "average revenue by state" carries no
        # aggregation of its own — take it from the wording so it doesn't sum.
        if plan.get("kind") == "chart" and not plan.get("agg"):
            plan["agg"] = self._requested_agg(command)

        note = self._inferred_note(plan, named)

        if plan["kind"] == "kpi":
            kpi_widget = self._build_kpi(ctx, plan)
            # "average revenue by month" is legitimately either a number or a
            # trend — offer both rather than silently guessing.
            chart_alt = self._chart_alternative(ctx, command, plan)
            if chart_alt is not None:
                for option in (kpi_widget, chart_alt):
                    self._prepend_note(option, note)
                return ChartCommandResponse(
                    kind="choice",
                    message="That could be a single number or a chart — which did you mean?",
                    options=[kpi_widget, chart_alt],
                )
            self._prepend_note(kpi_widget, self._ungrouped_note(command, named, plan))
            self._prepend_note(kpi_widget, note)
            return self._propose(kpi_widget)

        chart = self._build_chart(ctx, plan)
        self._prepend_note(chart, note)
        return self._propose(chart)

    @staticmethod
    def _prepend_note(widget: WidgetOption, note: str | None) -> None:
        """Put the column-substitution note ahead of the coverage warnings."""
        if note:
            widget.warnings.insert(0, note)

    @staticmethod
    def _ungrouped_note(command: str, named: list, plan: dict) -> str | None:
        """Flag a "by <something>" that never resolved to a column.

        Returning just the single number would quietly answer a narrower
        question than the one asked — usually the grouping column is misspelt.
        """
        text = command.lower()
        if not any(w in text for w in (" by ", " per ", " each ")):
            return None
        measure = plan.get("column")
        groupable = [
            c for c in named
            if c.name != measure and c.semantic_type in (_CATEGORICAL_TYPES | _TEMPORAL_TYPES)
        ]
        if groupable:
            return None
        return (
            "You asked to group this, but the grouping column didn't match any in this dataset "
            "— check its spelling. Showing a single number instead."
        )

    @staticmethod
    def _inferred_note(plan: dict, named: list) -> str | None:
        """Describe columns the model chose that the user never actually typed.

        Usually a resolved typo ("sale prie" -> SALE_PRICE), which is genuinely
        helpful — but the user has to be told, because the same mechanism is how
        a wrong column would sneak in. The approval step is what makes trusting
        the model here safe.
        """
        referenced = {
            str(plan.get(key)) for key in ("x", "y", "column")
            if plan.get(key) and plan.get(key) != "count"
        }
        inferred = sorted(referenced - {c.name for c in named})
        if not inferred:
            return None
        cols = ", ".join(f"'{c}'" for c in inferred)
        verb = "wasn't" if len(inferred) == 1 else "weren't"
        return (
            f"{cols} {verb} named in your request — the AI picked this column. "
            "Check it's the one you meant before adding."
        )

    def _propose(self, widget: WidgetOption) -> ChartCommandResponse:
        """Return a widget as a proposal — the caller must approve it.

        Nothing an NL command produces is added to a dashboard automatically.
        The user sees what was built, how much data backs it and what was
        excluded, then decides. Low-confidence widgets say so more loudly, but
        every widget stops here.
        """
        low = widget.confidence < self.REVIEW_THRESHOLD or (
            widget.chart is not None and not widget.chart.data
        )
        message = (
            f"'{widget.label}' needs a look before you add it."
            if low
            else f"Review '{widget.label}' before adding it."
        )
        return ChartCommandResponse(
            kind="review", kpi=widget.kpi, chart=widget.chart, message=message,
            confidence=widget.confidence, warnings=widget.warnings,
        )

    # Below this share of usable rows, a widget must be confirmed by a human.
    REVIEW_THRESHOLD = 0.6

    def _build_kpi(self, ctx, plan: dict) -> WidgetOption:
        """Materialize a KPI plan and score how much data backs it."""
        kpi_id = f"kpi:{plan['agg']}:{plan['column']}"
        widget = self.recommender.materialize_kpi(ctx.df, ctx.profile, kpi_id)
        if widget is None:
            raise BadRequestException(f"Couldn't compute {plan['agg']} of '{plan['column']}'.")

        total = len(ctx.df)
        usable = int(pd.to_numeric(ctx.df[plan["column"]], errors="coerce").notna().sum()) if total else 0
        warnings: list[str] = []
        if total and usable < total:
            warnings.append(
                f"{total - usable} of {total} rows have no numeric '{plan['column']}' and were "
                f"excluded from the {plan['agg']}."
            )
        return WidgetOption(
            kind="kpi", label=widget["label"],
            description=f"A single {plan['agg']} across {usable:,} rows.",
            kpi=KpiCard(**widget),
            confidence=round(usable / total, 3) if total else 0.0,
            warnings=warnings,
        )

    def _build_chart(self, ctx, plan: dict) -> WidgetOption:
        """Materialize a chart plan, surfacing what was excluded and why."""
        y = plan.get("y") or "count"
        # Carry the requested aggregation into the id so "average revenue by
        # state" charts averages — a bare column name would silently sum.
        agg = str(plan.get("agg") or "").lower()
        if agg and agg != "sum" and y != "count" and plan["type"] in {"bar", "pie", "line"}:
            y = f"{agg}({y})"
        chart_id = f"chart:{plan['type']}:{plan['x']}" if plan["type"] == "hist" \
            else f"chart:{plan['type']}:{plan['x']}:{y}"
        widget = self.recommender.materialize_chart(ctx.df, ctx.profile, chart_id)
        if widget is None:
            raise BadRequestException(
                f"Couldn't build a {plan['type']} chart from those columns — check the column types."
            )

        meta = widget.get("meta") or {}
        total = int(meta.get("rows_total") or len(ctx.df))
        used = int(meta.get("rows_used") or 0)
        warnings = list(meta.get("notes") or [])
        return WidgetOption(
            kind="chart", label=widget["title"],
            description=f"A {widget['type']} chart over {used:,} of {total:,} rows.",
            chart=ChartSpec(**widget),
            confidence=round(used / total, 3) if total else 0.0,
            warnings=warnings,
        )

    def _chart_alternative(self, ctx, command: str, kpi_plan: dict) -> WidgetOption | None:
        """Return a chart reading of a KPI request, when one is plausible.

        Only triggers when the user named a grouping ("by region", "per month"),
        which is exactly when a single number may not be what they wanted.
        """
        text = command.lower()
        if not any(w in text for w in (" by ", " per ", "over time", "trend", "each ")):
            return None

        measure = kpi_plan["column"]
        temporal = [c for c in ctx.profile.columns if c.semantic_type in _TEMPORAL_TYPES]
        # Match the same way _named_columns does, so "prop class" finds
        # PROP_CLASS. Matching raw names only worked if the user typed the
        # underscore, and silently grouped by the wrong column otherwise.
        grouping = next(
            (
                c for c in self._named_columns(command, ctx.profile)
                if c.name != measure and c.semantic_type in _CATEGORICAL_TYPES
            ),
            None,
        )

        # The chart reading of a KPI request must use the SAME aggregation the
        # user asked for: "average revenue by state" charting totals answers a
        # different question, and the axis label makes the mismatch obvious.
        agg = kpi_plan.get("agg")
        if any(w in text for w in ("over time", "trend", "month", "year", "date")) and temporal:
            alt = {"kind": "chart", "type": "line", "x": temporal[0].name, "y": measure, "agg": agg}
        elif grouping is not None:
            alt = {"kind": "chart", "type": "bar", "x": grouping.name, "y": measure, "agg": agg}
        else:
            # The user asked to group by something we can't identify — offering a
            # chart of an arbitrary column would be a guess, so offer none.
            return None

        try:
            return self._build_chart(ctx, alt)
        except BadRequestException:
            return None

    def _plan_command(self, command: str, profile) -> dict | None:
        """Ask the LLM to translate the request into a widget plan."""
        llm = get_llm()
        if not llm.available:
            return None
        schema = ", ".join(f"{c.name}: {c.semantic_type}" for c in profile.columns)
        plan = llm.complete_json(
            prompts.CHART_COMMAND_SYSTEM,
            prompts.CHART_COMMAND_USER.format(schema=schema, command=command),
        )
        if not isinstance(plan, dict) or plan.get("kind") not in {"kpi", "chart", "error"}:
            return None
        return plan

    @staticmethod
    def _named_columns(command: str, profile) -> list:
        """Columns the user actually referred to, matching underscores loosely."""
        text = command.lower().replace("_", " ")
        return [
            c for c in sorted(profile.columns, key=lambda c: -len(c.name))
            if c.name.lower().replace("_", " ") in text
        ]

    @staticmethod
    def _plan_uses(plan: dict | None, named: list) -> bool:
        """Whether a plan honours the columns the user explicitly named.

        Charts must use all of them — "quantity vs revenue" charting revenue
        against something else is wrong. A KPI is a single number, so it can
        only honour the measure; any grouping the user asked for is offered
        separately as a chart alternative.
        """
        if not plan or plan.get("kind") == "error":
            return False
        names = {c.name for c in named}
        if plan.get("kind") == "kpi":
            return plan.get("column") in names
        referenced = {str(plan.get(k)) for k in ("x", "y") if plan.get(k)}
        return names.issubset(referenced)

    @staticmethod
    def _requested_agg(command: str) -> str | None:
        """The aggregation the wording asks for, or ``None`` to keep the default.

        Only avg/min/max need saying — SUM is the default for a measure charted
        by category, and "total" already means that.
        """
        text = command.lower()
        # Most specific first: "median" must not be caught by a looser match.
        for words, agg in (
            (("median", "50th percentile", "p50"), "median"),
            (("standard deviation", "std dev", "stddev", "spread of"), "stddev"),
            (("variance",), "variance"),
            (("distinct", "unique"), "count_distinct"),
            (("average", "avg", "mean"), "avg"),
            (("largest", "biggest", "maximum", "highest per", "max "), "max"),
            (("smallest", "minimum", "lowest per", "min "), "min"),
        ):
            if any(w in text for w in words):
                return agg
        return None

    @staticmethod
    def _explicit_intent(command: str, named: list) -> dict | None:
        """A plan derived from unambiguous wording, or ``None`` to ask the model.

        Only fires when the phrasing names the shape *and* the named columns
        support it, so it can never invent a widget the data can't back.
        """
        text = command.lower()
        numeric = [c for c in named if c.semantic_type in _NUMERIC_TYPES]
        temporal = [c for c in named if c.semantic_type in _TEMPORAL_TYPES]

        if any(w in text for w in (" vs ", " versus ", "scatter")) and len(numeric) >= 2:
            return {"kind": "chart", "type": "scatter", "x": numeric[0].name, "y": numeric[1].name}
        if any(w in text for w in ("distribution", "histogram")) and len(numeric) == 1:
            return {"kind": "chart", "type": "hist", "x": numeric[0].name, "y": None}
        if temporal and numeric and any(w in text for w in ("over time", "trend", "by month", "monthly")):
            return {"kind": "chart", "type": "line", "x": temporal[0].name, "y": numeric[0].name}
        return None

    @staticmethod
    def _plan_fits_types(plan: dict | None, profile) -> bool:
        """Whether the chart type is possible for the column types it names.

        Column names alone aren't enough: the model will happily plan a line
        chart over two numeric columns, which then parses a numeric axis as
        dates and produces a meaningless two-point trend.
        """
        if not plan:
            return False
        if plan.get("kind") != "chart":
            return True

        types = {c.name: c.semantic_type for c in profile.columns}
        x, y, kind = plan.get("x"), plan.get("y"), plan.get("type")
        if kind == "line":
            return types.get(x) in _TEMPORAL_TYPES and types.get(y) in _NUMERIC_TYPES
        if kind == "scatter":
            return types.get(x) in _NUMERIC_TYPES and types.get(y) in _NUMERIC_TYPES and x != y
        if kind == "hist":
            return types.get(x) in _NUMERIC_TYPES
        if kind in {"bar", "pie"}:
            return y == "count" or types.get(y) in _NUMERIC_TYPES
        return False

    @staticmethod
    def _unbuildable_message(named: list, profile) -> str:
        """Explain what was recognised and what is still missing.

        Usually a misspelt measure: the category matched, its partner didn't.
        Naming the recognised column and a concrete next command beats a
        generic "couldn't map that request".
        """
        recognised = ", ".join(c.name for c in named)
        has_measure = any(c.semantic_type in _NUMERIC_TYPES for c in named)
        category = next((c for c in named if c.semantic_type in _CATEGORICAL_TYPES), None)

        if category is not None and not has_measure:
            measure = next((c.name for c in profile.columns if c.semantic_type in _NUMERIC_TYPES), None)
            suggestion = (
                f'Try "{measure} by {category.name}" or "count by {category.name}".'
                if measure
                else f'Try "count by {category.name}".'
            )
            return (
                f"I recognised {recognised} but not the measure you asked to aggregate — "
                f"check its spelling. {suggestion}"
            )
        return (
            f"Couldn't build a widget from {recognised}. "
            "Try naming a category and a measure, e.g. \"revenue by region\"."
        )

    @staticmethod
    def _example_commands(profile) -> str:
        """Two concrete example prompts built from this dataset's own columns."""
        numeric = next((c.name for c in profile.columns if c.semantic_type in _NUMERIC_TYPES), None)
        category = next((c.name for c in profile.columns if c.semantic_type in _CATEGORICAL_TYPES), None)
        examples = []
        if numeric and category:
            examples.append(f'"{numeric} by {category}"')
        if numeric:
            examples.append(f'"average {numeric}"')
        elif category:
            examples.append(f'"count by {category}"')
        return " or ".join(examples)

    def _heuristic_command(self, command: str, profile) -> dict | None:
        """Keyword fallback when the LLM is unavailable or returned garbage."""
        text = command.lower()
        # Same loose matching as _named_columns, so "prop class" finds
        # PROP_CLASS. Matching raw names left this planner blind to every
        # underscored column, which is most of them in real warehouse exports.
        mentioned = self._named_columns(command, profile)
        numeric = [c for c in mentioned if c.semantic_type in _NUMERIC_TYPES]
        temporal = [c for c in mentioned if c.semantic_type in _TEMPORAL_TYPES]
        other = [c for c in mentioned if c not in numeric and c not in temporal]

        agg = None
        # Most specific first so "median" isn't swallowed by a looser word.
        for word, key in (("median", "median"), ("std dev", "stddev"), ("stddev", "stddev"),
                          ("standard deviation", "stddev"), ("variance", "variance"),
                          ("distinct", "count_distinct"), ("unique", "count_distinct"),
                          ("average", "avg"), ("avg", "avg"), ("mean", "avg"), ("total", "sum"),
                          ("sum", "sum"), ("max", "max"), ("highest", "max"), ("min", "min"),
                          ("lowest", "min"), ("count", "count"), ("how many", "count")):
            if word in text:
                agg = key
                break

        wants_chart = any(w in text for w in ("chart", "plot", "graph", "by ", "per ", "trend",
                                              "over time", "distribution", "vs", "versus",
                                              "pie", "bar", "line", "scatter", "histogram"))
        if agg and numeric and not wants_chart:
            return {"kind": "kpi", "agg": agg, "column": numeric[0].name}

        if ("distribution" in text or "histogram" in text) and numeric:
            return {"kind": "chart", "type": "hist", "x": numeric[0].name, "y": None}
        if ("scatter" in text or " vs" in text or "versus" in text) and len(numeric) >= 2:
            return {"kind": "chart", "type": "scatter", "x": numeric[0].name, "y": numeric[1].name}
        if (temporal or "trend" in text or "over time" in text) and numeric:
            time_col = temporal[0].name if temporal else next(
                (c.name for c in profile.columns if c.semantic_type in _TEMPORAL_TYPES), None)
            if time_col:
                return {"kind": "chart", "type": "line", "x": time_col, "y": numeric[0].name}
        if other:
            chart_type = "pie" if "pie" in text else "bar"
            if numeric:
                return {"kind": "chart", "type": chart_type, "x": other[0].name, "y": numeric[0].name}
            # The user asked to average/total something, but no numeric column
            # they named was recognised (usually a typo). Counting rows instead
            # would answer a different question, so let the caller explain.
            if agg and agg != "count":
                return None
            return {"kind": "chart", "type": chart_type, "x": other[0].name, "y": "count"}
        if numeric and agg:
            return {"kind": "kpi", "agg": agg, "column": numeric[0].name}
        return None

    def _load_selection(self, dataset_id: int) -> dict | None:
        """Load a saved selection, ignoring legacy/auto-spec rows."""
        saved = self.dashboards.latest_for_dataset(dataset_id)
        if saved is None:
            return None
        spec = saved.spec or {}
        kpis, charts = spec.get("kpis"), spec.get("charts")
        # Only accept the new format (lists of string ids).
        if (
            isinstance(kpis, list)
            and isinstance(charts, list)
            and all(isinstance(x, str) for x in kpis)
            and all(isinstance(x, str) for x in charts)
        ):
            return {"kpis": kpis, "charts": charts}
        return None
