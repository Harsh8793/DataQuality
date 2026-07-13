"""Profiling agent: infer types and compute per-column statistics."""

from __future__ import annotations

from app.agents.base import Agent, AgentContext, AgentResult
from app.core.engines.profiler import Profiler


class ProfilingAgent(Agent):
    """Wraps the deterministic profiler and stores the result on the context."""

    name = "profiling"

    def __init__(self) -> None:
        super().__init__()
        self._profiler = Profiler()

    def run(self, ctx: AgentContext) -> AgentResult:
        """Profile ``ctx.df`` and attach the result to the context."""
        if ctx.df is None:
            return self._fail("No dataframe to profile.")
        ctx.emit("progress", {"agent": self.name, "status": "running"})
        profile = self._profiler.profile(ctx.df)
        ctx.profile = profile
        ctx.emit("progress", {
            "agent": self.name, "status": "done",
            "summary": f"{profile.col_count} columns profiled",
        })
        return self._ok(profile)
