"""Quality agent: run checks and compute the six-dimension score."""

from __future__ import annotations

from app.agents.base import Agent, AgentContext, AgentResult
from app.core.engines.quality_checks import QualityEngine
from app.core.engines.scorer import Scorer


class QualityAgent(Agent):
    """Runs the quality engine and scorer, storing findings + score on ctx."""

    name = "quality"

    def __init__(self) -> None:
        super().__init__()
        self._engine = QualityEngine()
        self._scorer = Scorer()

    def run(self, ctx: AgentContext) -> AgentResult:
        """Execute all quality checks and score the dataset."""
        if ctx.df is None or ctx.profile is None:
            return self._fail("Profiling must run before quality analysis.")
        ctx.emit("progress", {"agent": self.name, "status": "running"})
        findings = self._engine.run(ctx.df, ctx.profile)
        score = self._scorer.score(findings, ctx.profile)
        ctx.findings = findings
        ctx.score = score
        ctx.emit("progress", {
            "agent": self.name, "status": "done",
            "summary": f"score {score.overall}/100, {len(findings)} issues",
        })
        return self._ok({"findings": findings, "score": score})
