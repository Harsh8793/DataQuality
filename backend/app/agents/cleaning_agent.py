"""Cleaning agent: apply deterministic cleaning transforms."""

from __future__ import annotations

from app.agents.base import Agent, AgentContext, AgentResult
from app.core.engines.cleaner import Cleaner, CleaningResult


class CleaningAgent(Agent):
    """Wraps the cleaning engine to produce a cleaned frame + audit trail."""

    name = "cleaning"

    def __init__(self) -> None:
        super().__init__()
        self._cleaner = Cleaner()

    def clean(self, ctx: AgentContext) -> CleaningResult:
        """Clean ``ctx.df`` and return the result (profile required)."""
        if ctx.df is None or ctx.profile is None:
            raise ValueError("Dataframe and profile are required for cleaning.")
        return self._cleaner.clean(ctx.df, ctx.profile)

    def run(self, ctx: AgentContext) -> AgentResult:
        """Run cleaning and stash the result in ``ctx.meta['cleaning']``."""
        try:
            result = self.clean(ctx)
        except ValueError as exc:
            return self._fail(str(exc))
        ctx.meta["cleaning"] = result
        return self._ok({"operations": result.operations, "rows": len(result.df)})
