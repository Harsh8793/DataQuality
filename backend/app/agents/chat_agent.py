"""Chat agent: reason like an analyst — converse or query only when needed."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.agents.base import Agent, AgentContext, AgentResult
from app.core.engines.chart_recommender import ChartRecommender
from app.core.engines.duckdb_engine import DuckDBEngine, QueryResult
from app.core.llm import get_llm
from app.core.llm.prompts import (
    CHAT_NARRATE_SYSTEM,
    CHAT_NARRATE_USER,
    CHAT_PLANNER_SYSTEM,
    CHAT_PLANNER_USER,
)
from app.exceptions.base import AppException

_GREETINGS = {"hi", "hello", "hey", "yo", "hola", "thanks", "thank you", "ok", "okay", "help"}
# Words that suggest the user actually wants to query the data.
_DATA_HINTS = (
    "average", "avg", "sum", "total", "count", "how many", "number of", "top", "highest",
    "lowest", "max", "min", "most", "least", "per ", " by ", "group", "trend", "distribution",
    "show", "list", "which", "where", "compare", "revenue", "price", "amount", "sales",
)


@dataclass
class ChatAnswer:
    """Full response to a chat-with-data question."""

    answer: str
    sql: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    row_count: int = 0
    chart_spec: dict | None = field(default=None)


class ChatAgent(Agent):
    """Plans each message (converse vs. query), then executes only if needed."""

    name = "chat"

    def __init__(self) -> None:
        super().__init__()
        self._duck = DuckDBEngine()
        self._llm = get_llm()
        self._recommender = ChartRecommender()

    def ask(self, ctx: AgentContext, question: str, history: list[dict] | None = None) -> ChatAnswer:
        """Answer a message: conversationally, or by querying the data.

        ``history`` is the recent conversation (``[{role, content}, ...]``) so
        follow-ups like "generate the graph" resolve against prior turns.
        """
        # "Give me insights / summarize this data" → run the insight generator
        # instead of refusing or dumping rows.
        if self._wants_insights(ctx, question):
            return self._answer_with_insights(ctx, question)

        plan = self._plan(ctx, question, history or [])
        # A plan with neither runnable SQL nor an actual reply is useless —
        # e.g. {"mode":"answer","answer":null} for "now show it as a pie chart".
        usable = (plan.get("mode") == "sql" and plan.get("sql")) or plan.get("answer")
        if not usable:
            plan = self._heuristic_plan(ctx, question, history or [])

        if plan.get("mode") == "sql" and plan.get("sql"):
            chart = plan.get("chart")
            return self._answer_with_data(
                ctx, question, str(plan["sql"]),
                forced_chart=chart if chart in {"bar", "pie", "line", "scatter"} else None,
            )

        # Conversational / meta / unanswerable → direct reply, no SQL, no table.
        answer = plan.get("answer") or self._fallback_answer(ctx)
        return ChatAnswer(answer=str(answer))

    def run(self, ctx: AgentContext) -> AgentResult:
        """Answer the question in ``ctx.meta['question']``."""
        question = ctx.meta.get("question")
        if not question:
            return self._fail("No question provided.")
        try:
            return self._ok(self.ask(ctx, question))
        except Exception as exc:  # noqa: BLE001
            return self._fail(str(exc))

    # ---- planning ----------------------------------------------------- #
    def _plan(self, ctx: AgentContext, question: str, history: list[dict]) -> dict:
        """Decide whether to converse or query, using the LLM (with fallback)."""
        if not self._llm.available:
            return self._heuristic_plan(ctx, question)
        raw = self._llm.complete_json(
            CHAT_PLANNER_SYSTEM,
            CHAT_PLANNER_USER.format(
                schema=self._schema(ctx), samples=self._samples(ctx),
                history=self._history_text(history), question=question,
            ),
        )
        if isinstance(raw, dict) and raw.get("mode") in {"sql", "answer"}:
            return raw
        return self._heuristic_plan(ctx, question, history)

    @staticmethod
    def _history_text(history: list[dict]) -> str:
        """Compact the last few turns for the planner prompt."""
        if not history:
            return "(none)"
        lines = [f"{m.get('role')}: {str(m.get('content', ''))[:200]}" for m in history[-8:]]
        return "\n".join(lines)

    def _heuristic_plan(self, ctx: AgentContext, question: str, history: list[dict] | None = None) -> dict:
        """Deterministic fallback when the LLM is unavailable/rate-limited."""
        q = question.lower().strip().rstrip("!.?")
        if q in _GREETINGS or len(q.split()) <= 1:
            return {"mode": "answer", "answer": self._greeting()}

        # Chart intent: pick the requested type and aggregate sensibly.
        chart = None
        if any(w in q for w in ("graph", "chart", "plot", "visual")):
            chart = ("pie" if "pie" in q else "line" if ("line" in q or "trend" in q)
                     else "scatter" if "scatter" in q else "bar")

        # Recognized analytic patterns (avg/sum/top-N/count/trend) get real SQL.
        sql = self._pattern_sql(ctx, q, default_agg="AVG" if chart else None)
        if sql:
            return {"mode": "sql", "sql": sql, "chart": chart}
        if chart:
            # "Generate the graph" follow-up: chart the last query we ran.
            for m in reversed(history or []):
                if m.get("sql"):
                    return {"mode": "sql", "sql": m["sql"], "chart": chart}
            return {
                "mode": "answer",
                "answer": "Tell me what to plot — name a measure and a category, e.g. "
                "\"bar graph of SALE_PRICE by PROP_CLASS\" or \"trend of SALE_PRICE over SALE_DATE\".",
            }
        # Only query the data when the question actually looks data-related.
        if any(hint in q for hint in _DATA_HINTS):
            return {"mode": "sql", "sql": f"SELECT * FROM {self._duck.TABLE} LIMIT 20"}
        return {
            "mode": "answer",
            "answer": "I focus on this dataset. Ask me about your data — for example totals, "
            "averages, counts, top values, or a specific record.",
        }

    def _pattern_sql(self, ctx: AgentContext, q: str, default_agg: str | None = None) -> str | None:
        """Build real GROUP-BY SQL for common analytic phrasings, no LLM needed.

        Handles the shapes our own starter questions use: "average X by Y",
        "total/sum X by Y", "top N Y by X", "count/rows per Y",
        "trend of X over T", and "min/max/average of X".
        """
        table = self._duck.TABLE
        numeric, mentioned = self._mentioned_columns(ctx, q)
        if not mentioned:
            return None

        def col(name: str) -> str:
            return '"' + name.replace('"', '""') + '"'

        agg = None
        for word, fn in (("average", "AVG"), ("avg", "AVG"), ("mean", "AVG"), ("total", "SUM"),
                         ("sum", "SUM"), ("highest", "MAX"), ("max", "MAX"), ("lowest", "MIN"),
                         ("min", "MIN")):
            if word in q:
                agg = fn
                break

        num_cols = [c for c in mentioned if c in numeric]
        cat_cols = [c for c in mentioned if c not in numeric]

        # "top 5 Y by (total) X" — ranked categories by an aggregated measure.
        top = re.search(r"top\s+(\d+)", q)
        if top and cat_cols and num_cols:
            n = min(int(top.group(1)), 100)
            fn = agg or "SUM"
            return (f"SELECT {col(cat_cols[0])}, {fn}({col(num_cols[0])}) AS {fn.lower()}_value "
                    f"FROM {table} GROUP BY 1 ORDER BY 2 DESC LIMIT {n}")

        # "average/total X by/per Y" — classic group-by aggregate. Chart asks
        # like "bar graph of price by class" default to AVG when no agg word.
        effective_agg = agg or default_agg
        if effective_agg and num_cols and cat_cols and (" by " in q or " per " in q):
            return (f"SELECT {col(cat_cols[0])}, {effective_agg}({col(num_cols[0])}) "
                    f"AS {effective_agg.lower()}_value "
                    f"FROM {table} GROUP BY 1 ORDER BY 2 DESC LIMIT 25")

        # "how many rows per Y" / "count by Y" — frequency table.
        if ("count" in q or "how many" in q or "rows per" in q) and cat_cols:
            return (f"SELECT {col(cat_cols[0])}, COUNT(*) AS count "
                    f"FROM {table} GROUP BY 1 ORDER BY 2 DESC LIMIT 25")

        # "trend of X over T" — measure over a (date) column.
        if ("trend" in q or "over time" in q or " over " in q) and num_cols and len(mentioned) >= 2:
            time_col = next((c for c in mentioned if c not in num_cols), None) or (
                mentioned[1] if len(mentioned) > 1 else None)
            if time_col and time_col != num_cols[0]:
                return (f"SELECT {col(time_col)}, SUM({col(num_cols[0])}) AS total "
                        f"FROM {table} GROUP BY 1 ORDER BY 1 LIMIT 500")

        # "relationship between X and Y" — raw pairs for eyeballing.
        if ("relationship" in q or "correlation" in q) and len(num_cols) >= 2:
            return f"SELECT {col(num_cols[0])}, {col(num_cols[1])} FROM {table} LIMIT 200"

        # "min, max and average of X" — one-row summary stats.
        if agg and num_cols and not cat_cols:
            c = col(num_cols[0])
            return (f"SELECT MIN({c}) AS min, MAX({c}) AS max, ROUND(AVG({c}), 2) AS avg "
                    f"FROM {table}")
        return None

    def _mentioned_columns(self, ctx: AgentContext, q: str) -> tuple[set[str], list[str]]:
        """Return (numeric column names, columns mentioned in the question in order)."""
        if ctx.profile is not None:
            names = [c.name for c in ctx.profile.columns]
            numeric = {c.name for c in ctx.profile.columns
                       if c.semantic_type in {"numeric", "integer", "currency"}}
        else:
            names = [str(c) for c in ctx.df.columns]
            numeric = {str(c) for c in ctx.df.columns
                       if str(ctx.df[c].dtype).startswith(("int", "float"))}
        found = []
        for name in names:
            needle = name.lower()
            pos = q.find(needle)
            # Users often write "sale price" for the SALE_PRICE column.
            if pos < 0 and "_" in needle:
                pos = q.find(needle.replace("_", " "))
            if pos >= 0:
                found.append((pos, name))
        found.sort()
        return numeric, [name for _, name in found]

    # ---- insights path -------------------------------------------------- #
    _INSIGHT_HINTS = (
        "insight", "key finding", "summarize the data", "summary of the data",
        "summarize this data", "tell me about the data", "tell me about this data",
        "about this dataset", "analyze the data", "analyze this data",
        "overview of the data", "what do you see", "interesting about",
    )

    def _wants_insights(self, ctx: AgentContext, question: str) -> bool:
        """True for dataset-level insight/summary asks (not column questions)."""
        q = question.lower()
        if not any(h in q for h in self._INSIGHT_HINTS):
            return False
        # If a specific column is named, treat it as a normal data question.
        _, mentioned = self._mentioned_columns(ctx, q)
        return not mentioned

    def _answer_with_insights(self, ctx: AgentContext, question: str) -> ChatAnswer:
        from app.agents.insight_agent import InsightAgent

        wanted = re.search(r"top\s+(\d+)", question.lower())
        n = min(int(wanted.group(1)), 10) if wanted else 3

        insights = InsightAgent().generate_insights(ctx)[:n]
        if not insights:
            return ChatAnswer(answer=self._fallback_answer(ctx))

        lines = []
        for i, ins in enumerate(insights, 1):
            line = f"{i}. {ins.get('title', 'Insight')}: {ins.get('insight', '')}"
            if ins.get("action"):
                line += f" → {ins['action']}"
            lines.append(line)
        return ChatAnswer(
            answer="Here are the top insights from your data:\n\n" + "\n\n".join(lines)
            + "\n\nThe Insights tab has the full list."
        )

    # ---- data path ---------------------------------------------------- #
    def _answer_with_data(
        self, ctx: AgentContext, question: str, sql: str, forced_chart: str | None = None
    ) -> ChatAnswer:
        try:
            result = self._duck.execute(ctx.df, sql)
        except AppException:
            # Bad/invalid SQL — respond like an analyst instead of dumping data.
            return ChatAnswer(
                answer="I couldn't turn that into a valid query on this dataset. "
                "Try naming a column or metric, e.g. 'average revenue by state'."
            )
        answer = self._narrate(question, result)
        return ChatAnswer(
            answer=answer, sql=result.sql, columns=result.columns,
            rows=result.rows, row_count=result.row_count,
            chart_spec=self._maybe_chart(result, forced_chart),
        )

    def _narrate(self, question: str, result: QueryResult) -> str:
        if result.row_count == 0:
            return "No matching records were found for that question in this dataset."
        preview = json.dumps(result.rows[:10])[:1200]
        text = self._llm.complete(
            CHAT_NARRATE_SYSTEM, CHAT_NARRATE_USER.format(question=question, result=preview)
        )
        return text.strip() if text else self._fallback_narrate(result)

    @staticmethod
    def _fallback_narrate(result: QueryResult) -> str:
        """Deterministic one-liner when the LLM can't narrate the result."""
        def fmt(v) -> str:
            n = float(v)
            return f"{n:,.0f}" if n.is_integer() else f"{n:,.2f}"

        # Two-column category/measure results: call out the extremes.
        if len(result.columns) == 2 and result.row_count >= 2:
            cat, measure = result.columns
            try:
                valid = [r for r in result.rows if r.get(measure) is not None]
                ranked = sorted(valid, key=lambda r: float(r[measure]), reverse=True)
                if len(ranked) >= 2:
                    top, low = ranked[0], ranked[-1]
                    return (
                        f"{result.row_count} groups — highest {measure}: {top[cat]} "
                        f"({fmt(top[measure])}), lowest: {low[cat]} ({fmt(low[measure])})."
                    )
            except (TypeError, ValueError, KeyError):
                pass
        # Single-row summary (e.g. min/max/avg): read the values out.
        if result.row_count == 1 and result.rows:
            pairs = ", ".join(f"{k}: {v}" for k, v in result.rows[0].items())
            return f"Here's the summary — {pairs}."
        return f"Returned {result.row_count} row(s)."

    def _maybe_chart(self, result: QueryResult, forced: str | None = None) -> dict | None:
        """Build a chart for 2-column results, honoring a requested type."""
        if result.row_count == 0 or len(result.columns) != 2:
            return None
        a, b = result.columns

        def is_numeric(name: str) -> bool:
            for r in result.rows:
                v = r.get(name)
                if v is None:
                    continue
                try:
                    float(v)
                    return True
                except (TypeError, ValueError):
                    return False
            return False

        a_num, b_num = is_numeric(a), is_numeric(b)

        if forced == "scatter" and a_num and b_num:
            data = [{"x": float(r[a]), "y": float(r[b])} for r in result.rows[:300]
                    if r.get(a) is not None and r.get(b) is not None]
            return {"type": "scatter", "title": f"{a} vs {b}", "x": "x", "y": "y", "data": data} if data else None

        # Category/measure: whichever column is numeric is the measure, so the
        # chart works regardless of the SQL's column order.
        if a_num and not b_num:
            cat, measure = b, a
        elif b_num and not a_num:
            cat, measure = a, b
        elif a_num and b_num:
            cat, measure = a, b
        else:
            return None
        try:
            data = [{"name": str(r[cat]), "value": float(r[measure])}
                    for r in result.rows[:12] if r.get(measure) is not None]
        except (TypeError, ValueError):
            return None
        if not data:
            return None
        chart_type = forced if forced in {"bar", "pie", "line"} else ("pie" if len(data) <= 6 else "bar")
        return {"type": chart_type, "title": f"{measure} by {cat}", "x": "name", "y": "value", "data": data}

    # ---- helpers ------------------------------------------------------ #
    def _schema(self, ctx: AgentContext) -> str:
        if ctx.profile is not None:
            return ", ".join(f"{c.name}: {c.semantic_type}" for c in ctx.profile.columns)
        return ", ".join(f"{c}: {ctx.df[c].dtype}" for c in ctx.df.columns)

    def _samples(self, ctx: AgentContext) -> str:
        try:
            return json.dumps(ctx.df.head(3).astype(str).to_dict(orient="records"))[:1500]
        except Exception:  # noqa: BLE001
            return "[]"

    def _greeting(self) -> str:
        return (
            "Hi! I'm your data analyst for this dataset. Ask me things like totals, "
            "averages, counts, top values, breakdowns by a category, or about a specific record."
        )

    def _fallback_answer(self, ctx: AgentContext) -> str:
        cols = ", ".join(c.name for c in ctx.profile.columns[:8]) if ctx.profile else "your columns"
        return f"{self._greeting()} This dataset includes: {cols}."
