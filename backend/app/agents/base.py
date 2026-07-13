"""Agent base contracts shared by every agent."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.core.engines.profiler import DatasetProfile
from app.core.engines.quality_checks import QualityFinding
from app.core.engines.scorer import QualityScore
from app.core.logging import get_logger

ProgressFn = Callable[[str, dict], None]


@dataclass
class AgentContext:
    """Shared state threaded through an analysis pipeline.

    Agents read the fields they need and enrich the context for later agents.
    """

    dataset_id: str
    dataset_name: str
    df: pd.DataFrame
    profile: DatasetProfile | None = None
    findings: list[QualityFinding] = field(default_factory=list)
    score: QualityScore | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    _emit: ProgressFn | None = None

    def emit(self, event: str, payload: dict) -> None:
        """Emit a progress event to any attached listener (e.g. SSE)."""
        if self._emit is not None:
            self._emit(event, payload)


@dataclass
class AgentResult:
    """Uniform result envelope returned by every agent."""

    agent: str
    ok: bool
    data: Any = None
    error: str | None = None


class Agent(ABC):
    """Abstract base class for all agents."""

    name: str = "agent"

    def __init__(self) -> None:
        self.logger = get_logger(f"agent.{self.name}")

    @abstractmethod
    def run(self, ctx: AgentContext) -> AgentResult:
        """Execute the agent against the shared context."""

    def _ok(self, data: Any = None) -> AgentResult:
        return AgentResult(agent=self.name, ok=True, data=data)

    def _fail(self, error: str) -> AgentResult:
        self.logger.warning("Agent '%s' degraded: %s", self.name, error)
        return AgentResult(agent=self.name, ok=False, error=error)
