"""SQL agent: translate a natural-language question into safe DuckDB SQL."""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.agents.base import Agent, AgentContext, AgentResult
from app.core.engines.duckdb_engine import DuckDBEngine
from app.core.llm import get_llm
from app.core.llm.prompts import NL_TO_SQL_SYSTEM, NL_TO_SQL_USER


@dataclass
class SqlPlan:
    """A generated SQL statement plus a short explanation."""

    sql: str
    explanation: str


class SqlAgent(Agent):
    """Uses the LLM to produce SQL, then validates it before execution."""

    name = "sql"

    def __init__(self) -> None:
        super().__init__()
        self._llm = get_llm()
        self._duck = DuckDBEngine()

    def generate(self, ctx: AgentContext, question: str) -> SqlPlan:
        """Generate validated SQL for a question against ``ctx.df``.

        Falls back to a simple preview query when the LLM is unavailable.
        """
        schema = self._schema(ctx)
        samples = self._samples(ctx)
        raw = self._llm.complete_json(
            NL_TO_SQL_SYSTEM,
            NL_TO_SQL_USER.format(schema=schema, samples=samples, question=question),
        )
        if isinstance(raw, dict) and raw.get("sql"):
            sql = self._duck.validate(str(raw["sql"]))
            return SqlPlan(sql=sql, explanation=str(raw.get("explanation", "")))
        # Deterministic fallback keeps chat usable without the LLM.
        return SqlPlan(sql=f"SELECT * FROM {self._duck.TABLE} LIMIT 20",
                       explanation="Showing a preview (AI SQL unavailable).")

    def run(self, ctx: AgentContext) -> AgentResult:
        """Generate SQL for the question in ``ctx.meta['question']``."""
        question = ctx.meta.get("question")
        if not question:
            return self._fail("No question provided.")
        try:
            plan = self.generate(ctx, question)
        except Exception as exc:  # noqa: BLE001
            return self._fail(str(exc))
        return self._ok(plan)

    def _schema(self, ctx: AgentContext) -> str:
        if ctx.profile is not None:
            return ", ".join(f"{c.name}: {c.semantic_type}" for c in ctx.profile.columns)
        return ", ".join(f"{c}: {ctx.df[c].dtype}" for c in ctx.df.columns)

    def _samples(self, ctx: AgentContext) -> str:
        try:
            return json.dumps(ctx.df.head(3).astype(str).to_dict(orient="records"))[:1500]
        except Exception:  # noqa: BLE001
            return "[]"
