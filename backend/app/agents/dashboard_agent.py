"""Dashboard agent: recommend KPIs and charts from the profile."""

from __future__ import annotations

from app.agents.base import Agent, AgentContext, AgentResult
from app.core.engines.chart_recommender import ChartRecommender


class DashboardAgent(Agent):
    """Wraps the chart recommender to build an auto-dashboard spec."""

    name = "dashboard"

    def __init__(self) -> None:
        super().__init__()
        self._recommender = ChartRecommender()

    def build(self, ctx: AgentContext) -> dict:
        """Build the dashboard spec for ``ctx.df`` (profile required)."""
        if ctx.df is None or ctx.profile is None:
            raise ValueError("Dataframe and profile are required for the dashboard.")
        return self._recommender.build(ctx.df, ctx.profile)

    def run(self, ctx: AgentContext) -> AgentResult:
        """Produce the dashboard spec and return it."""
        try:
            spec = self.build(ctx)
        except ValueError as exc:
            return self._fail(str(exc))
        return self._ok(spec)
