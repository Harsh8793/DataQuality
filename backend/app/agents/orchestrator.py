"""Analysis orchestrator: runs the agent pipeline over a shared context.

The coordinator is deliberately DB- and API-free. It sequences agents,
isolates individual failures, and emits progress events (for SSE). Services
handle building the context and persisting results.

The ``Coordinator`` protocol leaves room to swap in a CrewAI/LangGraph
implementation later without touching the service layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.agents.base import AgentContext, AgentResult
from app.agents.governance_agent import GovernanceAgent
from app.agents.profiling_agent import ProfilingAgent
from app.agents.quality_agent import QualityAgent
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PipelineOutput:
    """Aggregated output of a full analysis pipeline run."""

    results: dict[str, AgentResult] = field(default_factory=dict)

    def get(self, agent: str) -> AgentResult | None:
        return self.results.get(agent)


class Coordinator(Protocol):
    """Interface for an analysis coordinator."""

    def run_analysis(self, ctx: AgentContext) -> PipelineOutput: ...


class SimpleCoordinator:
    """Sequential coordinator that enriches the context agent-by-agent."""

    def __init__(self) -> None:
        # Per-issue explanations are deterministic (engines/explanations.py) and
        # business insights are generated on demand by the Insights tab, so the
        # InsightAgent is intentionally NOT in the pipeline — keeps analysis fast
        # and token-free (it re-runs on every fix and edit).
        self._pipeline = [
            ProfilingAgent(),
            QualityAgent(),
            GovernanceAgent(),
        ]

    def run_analysis(self, ctx: AgentContext) -> PipelineOutput:
        """Run every pipeline agent in order, isolating failures."""
        output = PipelineOutput()
        for agent in self._pipeline:
            try:
                result = agent.run(ctx)
            except Exception as exc:  # noqa: BLE001 - one agent must not crash the run
                logger.exception("Agent '%s' crashed: %s", agent.name, exc)
                ctx.emit("progress", {"agent": agent.name, "status": "error", "summary": str(exc)})
                result = AgentResult(agent=agent.name, ok=False, error=str(exc))
            output.results[agent.name] = result
        ctx.emit("done", {"summary": "Analysis complete"})
        return output


_coordinator: SimpleCoordinator | None = None


def get_coordinator() -> SimpleCoordinator:
    """Return a process-wide coordinator instance."""
    global _coordinator
    if _coordinator is None:
        _coordinator = SimpleCoordinator()
    return _coordinator
