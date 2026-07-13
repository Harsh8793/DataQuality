"""Dashboard service: build the widget pool and manage a user's custom layout."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.agents.dashboard_agent import DashboardAgent
from app.agents.profiling_agent import ProfilingAgent
from app.constants.enums import SemanticType
from app.core.engines.chart_recommender import ChartRecommender
from app.core.llm import prompts
from app.core.llm.groq_client import get_llm
from app.exceptions.base import BadRequestException
from app.repositories.report_repository import DashboardRepository
from app.schemas.ai import ChartCommandResponse
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

        plan = self._plan_command(command, ctx.profile) or self._heuristic_command(command, ctx.profile)
        if plan is None or plan.get("kind") == "error":
            raise BadRequestException(
                plan.get("message") if plan else
                "Couldn't map that request to your columns. Try naming a column, e.g. "
                "\"average <numeric column> by <category column>\"."
            )

        if plan["kind"] == "kpi":
            kpi_id = f"kpi:{plan['agg']}:{plan['column']}"
            widget = self.recommender.materialize_kpi(ctx.df, ctx.profile, kpi_id)
            if widget is None:
                raise BadRequestException(f"Couldn't compute {plan['agg']} of '{plan['column']}'.")
            return ChartCommandResponse(kind="kpi", kpi=KpiCard(**widget),
                                        message=f"Created KPI: {widget['label']}")

        y = plan.get("y") or "count"
        chart_id = f"chart:{plan['type']}:{plan['x']}" if plan["type"] == "hist" \
            else f"chart:{plan['type']}:{plan['x']}:{y}"
        widget = self.recommender.materialize_chart(ctx.df, ctx.profile, chart_id)
        if widget is None:
            raise BadRequestException(
                f"Couldn't build a {plan['type']} chart from those columns — check the column types."
            )
        return ChartCommandResponse(kind="chart", chart=ChartSpec(**widget),
                                    message=f"Created chart: {widget['title']}")

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

    def _heuristic_command(self, command: str, profile) -> dict | None:
        """Keyword fallback when the LLM is unavailable or returned garbage."""
        text = command.lower()
        # Match columns by name mention, longest names first to avoid substrings.
        mentioned = [
            c for c in sorted(profile.columns, key=lambda c: -len(c.name))
            if c.name.lower() in text
        ]
        numeric = [c for c in mentioned if c.semantic_type in _NUMERIC_TYPES]
        temporal = [c for c in mentioned if c.semantic_type in _TEMPORAL_TYPES]
        other = [c for c in mentioned if c not in numeric and c not in temporal]

        agg = None
        for word, key in (("average", "avg"), ("avg", "avg"), ("mean", "avg"), ("total", "sum"),
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
            y = numeric[0].name if numeric else "count"
            return {"kind": "chart", "type": chart_type, "x": other[0].name, "y": y}
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
