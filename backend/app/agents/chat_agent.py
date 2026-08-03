"""Chat agent: reason like an analyst — converse or query only when needed."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import pandas as pd

from app.agents.base import Agent, AgentContext, AgentResult
from app.constants.enums import SemanticType
from app.core.engines.chart_recommender import ChartRecommender, parse_dates
from app.core.engines.duckdb_engine import DuckDBEngine, QueryResult
from app.core.llm import get_llm
from app.core.llm.prompts import (
    CHAT_NARRATE_SYSTEM,
    CHAT_NARRATE_USER,
    CHAT_PLANNER_SYSTEM,
    CHAT_PLANNER_USER,
)
from app.exceptions.base import AppException

_TEMPORAL = {SemanticType.DATE, SemanticType.DATETIME}
_TEXTUAL = {SemanticType.CATEGORICAL, SemanticType.TEXT, SemanticType.BOOLEAN}

_TEMPORAL = {SemanticType.DATE, SemanticType.DATETIME}
_TEXTUAL = {SemanticType.CATEGORICAL, SemanticType.TEXT, SemanticType.BOOLEAN}

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

        # Dataset-level "how many rows/records" → answer deterministically so the
        # LLM can't deflect with "please run a SQL query".
        if self._is_rowcount_question(question):
            return self._answer_with_data(
                ctx, question, f"SELECT COUNT(*) AS row_count FROM {self._duck.TABLE}"
            )

        plan = self._plan(ctx, question, history or [])
        # A plan with neither runnable SQL nor an actual reply is useless —
        # e.g. {"mode":"answer","answer":null} for "now show it as a pie chart".
        usable = (plan.get("mode") == "sql" and plan.get("sql")) or plan.get("answer")
        # The LLM sometimes returns a lazy non-answer for a data question
        # ("please run a SQL query…", "I don't have access…"). Treat that as
        # unusable and fall back to the deterministic planner.
        if plan.get("mode") == "answer" and self._is_deflection(plan.get("answer")):
            usable = False
        if not usable:
            plan = self._heuristic_plan(ctx, question, history or [])

        if plan.get("mode") == "sql" and plan.get("sql"):
            chart = plan.get("chart")
            # Deterministic backup query: if the planned SQL fails to execute
            # (bad column, uncast compare, Groq hiccup), retry with this.
            fallback_sql = self._pattern_sql(ctx, question.lower().strip().rstrip("!.?"))
            return self._answer_with_data(
                ctx, question, str(plan["sql"]),
                forced_chart=chart if chart in {"bar", "pie", "line", "scatter"} else None,
                fallback_sql=fallback_sql,
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
        "trend of X over T", "min/max/average of X", and value filters like
        "average X in <category value>" (e.g. "average revenue in Texas").
        """
        table = self._duck.TABLE
        numeric, mentioned = self._mentioned_columns(ctx, q)

        def col(name: str) -> str:
            return '"' + name.replace('"', '""') + '"'

        # Detect an "in/for <category value>" filter (e.g. state = 'Texas').
        where = ""
        filt = self._filter_clause(ctx, q)
        if filt:
            fcol, fval = filt
            esc = fval.lower().replace("'", "''")
            where = f" WHERE LOWER(CAST({col(fcol)} AS VARCHAR)) = '{esc}'"

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
                    f"FROM {table}{where} GROUP BY 1 ORDER BY 2 DESC LIMIT {n}")

        # "average/total X by/per Y" — classic group-by aggregate. Chart asks
        # like "bar graph of price by class" default to AVG when no agg word.
        effective_agg = agg or default_agg
        if effective_agg and num_cols and cat_cols and (" by " in q or " per " in q):
            return (f"SELECT {col(cat_cols[0])}, {effective_agg}({col(num_cols[0])}) "
                    f"AS {effective_agg.lower()}_value "
                    f"FROM {table}{where} GROUP BY 1 ORDER BY 2 DESC LIMIT 25")

        # "how many rows per Y" / "count by Y" — frequency table.
        if ("count" in q or "how many" in q or "rows per" in q) and cat_cols:
            return (f"SELECT {col(cat_cols[0])}, COUNT(*) AS count "
                    f"FROM {table}{where} GROUP BY 1 ORDER BY 2 DESC LIMIT 25")

        # "trend of X over T" — measure over a (date) column.
        if ("trend" in q or "over time" in q or " over " in q) and num_cols and len(mentioned) >= 2:
            time_col = next((c for c in mentioned if c not in num_cols), None) or (
                mentioned[1] if len(mentioned) > 1 else None)
            if time_col and time_col != num_cols[0]:
                return (f"SELECT {col(time_col)}, SUM({col(num_cols[0])}) AS total "
                        f"FROM {table}{where} GROUP BY 1 ORDER BY 1 LIMIT 500")

        # "relationship between X and Y" — raw pairs for eyeballing.
        if ("relationship" in q or "correlation" in q) and len(num_cols) >= 2:
            return f"SELECT {col(num_cols[0])}, {col(num_cols[1])} FROM {table}{where} LIMIT 200"

        # "average revenue in Texas" — a single aggregated measure, optionally
        # filtered to one category value.
        if agg and num_cols and not cat_cols:
            c = col(num_cols[0])
            if where:
                return f"SELECT {agg}(TRY_CAST({c} AS DOUBLE)) AS {agg.lower()}_value FROM {table}{where}"
            return (f"SELECT MIN({c}) AS min, MAX({c}) AS max, ROUND(AVG({c}), 2) AS avg "
                    f"FROM {table}")

        # "how many rows in Texas" — filtered row count with no measure named.
        if where and ("count" in q or "how many" in q or "number of" in q):
            return f"SELECT COUNT(*) AS count FROM {table}{where}"

        # Any other question that named a category value → show those rows.
        if where:
            return f"SELECT * FROM {table}{where} LIMIT 50"

        return None

    def _filter_clause(self, ctx: AgentContext, q: str) -> tuple[str, str] | None:
        """Find a category value named in the question (e.g. "Texas" -> state).

        Returns ``(column_name, value)`` for the longest matching value, or
        ``None``. Only low-cardinality categorical/text columns are scanned so a
        common English word can't accidentally match a free-text field. ``q`` is
        expected lower-cased; matching is word-boundary aware.
        """
        if ctx.profile is None:
            return None
        best: tuple[int, str, str] | None = None
        for c in ctx.profile.columns:
            if c.semantic_type not in {"categorical", "text", "boolean"}:
                continue
            if c.distinct_count and c.distinct_count > 60:
                continue
            try:
                values = ctx.df[c.name].dropna().astype(str).unique()
            except Exception:  # noqa: BLE001
                continue
            for v in values:
                vs = str(v).strip()
                if len(vs) < 2:
                    continue
                # Allow a simple plural: users ask "for laptops" about a
                # `product` column whose value is "Laptop".
                if re.search(r"\b" + re.escape(vs.lower()) + r"(?:e?s)?\b", q) and (
                    best is None or len(vs) > best[0]
                ):
                    best = (len(vs), c.name, vs)
        return (best[1], best[2]) if best else None

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

    # Structural/filler words that don't add a condition to a count question.
    _COUNT_FILLER = {
        "how", "many", "number", "count", "of", "total", "the", "a", "an", "is", "are", "there",
        "in", "dataset", "data", "table", "does", "do", "did", "have", "has", "had", "contain",
        "contains", "hold", "holds", "got", "it", "this", "that", "present", "currently", "overall",
        "altogether", "approximately", "tell", "me", "whats", "what", "s", "size", "rows", "row",
        "records", "record", "entries", "entry", "observations", "observation", "datapoints",
    }

    @classmethod
    def _is_rowcount_question(cls, question: str) -> bool:
        """True ONLY for whole-dataset row counts, not 'how many rows have <X>'.

        We require a count intent + a rows/records noun, and that nothing
        meaningful remains after removing filler words (so a condition like
        'have missing revenue' disqualifies it → the LLM handles that).
        """
        q = question.lower().strip().rstrip("?.!")
        if not re.search(r"\b(how many|number of|count of|total|count|size)\b", q):
            return False
        if not re.search(r"\b(rows?|records?|entries|entry|observations?|data ?points?)\b", q):
            return False
        leftover = [t for t in re.findall(r"[a-z]+", q) if t not in cls._COUNT_FILLER]
        return not leftover

    @staticmethod
    def _is_deflection(answer: str | None) -> bool:
        """Detect an LLM non-answer that should have queried the data instead."""
        if not answer:
            return True
        a = answer.lower()
        tells = (
            "run a sql", "run the sql", "execute a sql", "write a sql", "use a sql",
            "i don't have access", "i cannot access", "i can't access", "unable to access",
            "please provide the data", "no access to the data",
        )
        return any(t in a for t in tells)

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
        self, ctx: AgentContext, question: str, sql: str,
        forced_chart: str | None = None, fallback_sql: str | None = None,
    ) -> ChatAnswer:
        frame, caveats = self._query_frame(ctx)
        text_columns = self._text_columns(ctx)
        # A query that computes the wrong statistic returns a real number, so
        # nothing downstream can detect it. Swap the single aggregate for the
        # one the question actually asked for.
        wanted = self._aggregate_mismatch(question, sql)
        if wanted:
            sql = re.sub(
                rf"\b({'|'.join(self._AGG_FUNCS)})\s*\(", f"{wanted}(", sql, count=1, flags=re.IGNORECASE
            )
        filters = self._equality_filters(sql, text_columns)
        sql = self._normalize_text_filters(sql, text_columns)
        if fallback_sql:
            fallback_sql = self._normalize_text_filters(fallback_sql, text_columns)
        try:
            result = self._duck.execute(frame, sql)
        except AppException:
            # Planned SQL failed — retry once with a deterministic query before
            # giving up, so filtered asks still work when the LLM slips.
            if fallback_sql and fallback_sql != sql:
                try:
                    result = self._duck.execute(frame, fallback_sql)
                except AppException:
                    return self._invalid_query_answer()
            else:
                return self._invalid_query_answer()

        answer = self._narrate(question, result)
        # Only mention data-quality caveats for columns this query actually
        # touched, so answers don't carry irrelevant noise.
        notes = [n for n in caveats if self._note_applies(n, result.sql)]
        dropped = self._dropped_filter_note(ctx, question, result.sql)
        if dropped:
            notes.insert(0, dropped)
        notes += self._variant_caveats(frame, filters)
        notes += self._result_caveats(result)
        if notes:
            answer = answer.rstrip() + "\n\n" + "\n".join(f"Note: {n}" for n in notes)
        return ChatAnswer(
            answer=answer, sql=result.sql, columns=result.columns,
            rows=result.rows, row_count=result.row_count,
            chart_spec=self._maybe_chart(result, forced_chart),
        )

    # Matches `col = 'value'` / `"col" = 'value'`. Unquoted names may not contain
    # spaces — allowing them made the pattern swallow preceding SQL keywords
    # ("FROM dataset WHERE gender") and silently skip the rewrite.
    _EQUALITY = re.compile(r"(?<![\w(])(?:\"([^\"]+)\"|([A-Za-z_]\w*))\s*=\s*'([^']*)'")

    def _normalize_text_filters(self, sql: str, text_columns: set[str]) -> str:
        """Make equality filters on text columns case- and whitespace-insensitive.

        Uploaded categoricals are rarely clean: ``state`` holds "California" and
        "california", ``gender`` holds "m" and "M". An exact ``=`` silently
        matches one spelling and undercounts, which reads as a real answer.
        """
        lookup = {c.lower(): c for c in text_columns}

        def rewrite(match: re.Match) -> str:
            column = match.group(1) or match.group(2)
            value = match.group(3)
            real = lookup.get(column.strip().lower())
            if real is None:
                return match.group(0)
            return f"LOWER(TRIM(CAST(\"{real}\" AS VARCHAR))) = '{value.strip().lower()}'"

        return self._EQUALITY.sub(rewrite, sql)

    # Question wording -> the aggregate it asks for.
    _AGG_INTENT = (
        (("average", "avg ", "avg(", "mean"), "AVG"),
        (("total", "sum of", "combined", "altogether"), "SUM"),
        (("how many", "number of", "count of"), "COUNT"),
        (("largest", "biggest", "maximum"), "MAX"),
        (("smallest", "minimum"), "MIN"),
    )
    _AGG_FUNCS = ("AVG", "SUM", "COUNT", "MIN", "MAX")

    @classmethod
    def _aggregate_mismatch(cls, question: str, sql: str) -> str | None:
        """The aggregate the question asked for, when the SQL uses another one.

        The model sometimes writes ``SUM(...) AS avg_revenue`` and the narrator
        then calls a total an "average". The value is real, so no number-check
        can catch it — only comparing intent against the SQL does.
        """
        q = question.lower()
        wanted = next((agg for words, agg in cls._AGG_INTENT if any(w in q for w in words)), None)
        if wanted is None:
            return None
        used = [f for f in cls._AGG_FUNCS if re.search(rf"\b{f}\s*\(", sql, re.IGNORECASE)]
        # Only act when the query computes exactly one thing; multi-aggregate
        # summaries (min/max/avg together) are legitimately mixed.
        if len(used) == 1 and used[0].upper() != wanted:
            return wanted
        return None

    def _dropped_filter_note(self, ctx: AgentContext, question: str, sql: str) -> str | None:
        """Flag a value named in the question that never reached the SQL.

        "average revenue for laptops" answered with the average across every
        product looks entirely plausible and is simply a different question.
        Detected from the data itself, so it works on any dataset.
        """
        found = self._filter_clause(ctx, question.lower())
        if not found:
            return None
        column, value = found
        lowered = sql.lower()
        if value.lower() in lowered or f'"{column.lower()}"' in lowered or column.lower() in lowered:
            return None
        return (
            f"you mentioned '{value}', but this answer covers every row — it was NOT "
            f"filtered to {value} in '{column}'. Ask again naming the column if you "
            "wanted just those rows."
        )

    def _equality_filters(self, sql: str, text_columns: set[str]) -> list[tuple[str, str]]:
        """``(column, value)`` pairs from equality filters on text columns.

        Read from the SQL *before* normalisation — afterwards the column sits
        inside ``CAST(...)`` and the pattern no longer matches it.
        """
        lookup = {c.lower(): c for c in text_columns}
        pairs: list[tuple[str, str]] = []
        for match in self._EQUALITY.finditer(sql):
            column = (match.group(1) or match.group(2)).strip().lower()
            real = lookup.get(column)
            if real:
                pairs.append((real, match.group(3).strip().lower()))
        return pairs

    def _variant_caveats(self, frame: pd.DataFrame, filters: list[tuple[str, str]]) -> list[str]:
        """Warn when a filtered column holds other spellings of the same value.

        Case and whitespace are handled by normalising the comparison, but
        abbreviations ("m" vs "male") are a judgement call we refuse to make
        silently: the count is reported, and so is the ambiguity.
        """
        notes: list[str] = []
        for real, value in filters:
            if real not in frame.columns or not value:
                continue
            distinct = {
                str(v).strip().lower() for v in frame[real].dropna().unique()
            }
            related = sorted(
                v for v in distinct
                if v != value and (v.startswith(value) or value.startswith(v))
            )
            if related:
                shown = ", ".join(f"'{v}'" for v in related[:4])
                notes.append(
                    f"'{real}' also contains {shown}, which may mean the same thing as "
                    f"'{value}'. Only rows equal to '{value}' were counted — say which "
                    "spellings to include if you need them combined."
                )
        return notes

    @staticmethod
    def _note_applies(note: str, sql: str) -> bool:
        """Whether a column caveat is relevant to the SQL that ran."""
        match = re.search(r"'([^']+)'", note)
        return bool(match and match.group(1).lower() in sql.lower())

    def _result_caveats(self, result: QueryResult) -> list[str]:
        """Caveats about the result set itself: truncation, mostly."""
        if result.row_count >= self._duck.MAX_ROWS:
            return [
                f"only the first {self._duck.MAX_ROWS:,} rows are shown, so any total "
                "you compute from this table would be incomplete."
            ]
        # An ORDER BY ... LIMIT n is a deliberate "top n", not truncation.
        if re.search(r"\border\s+by\b", result.sql, re.IGNORECASE):
            return []
        limit = re.search(r"\blimit\s+(\d+)\s*$", result.sql, re.IGNORECASE)
        if limit and result.row_count >= int(limit.group(1)) and int(limit.group(1)) < self._duck.MAX_ROWS:
            return [
                f"this query was limited to {int(limit.group(1)):,} rows, so the list may be "
                "incomplete — ask for a count if you need the true total."
            ]
        return []

    @staticmethod
    def _invalid_query_answer() -> ChatAnswer:
        return ChatAnswer(
            answer="I couldn't turn that into a valid query on this dataset. "
            "Try naming a column or metric, e.g. 'average revenue by state'."
        )

    def _narrate(self, question: str, result: QueryResult) -> str:
        if result.row_count == 0:
            return "No matching records were found for that question in this dataset."
        # The model only ever sees a preview, so it must be told the real size —
        # otherwise it reports the preview length as the answer ("there are 10
        # customers" for 500 rows).
        preview = json.dumps(result.rows[:10])[:1200]
        text = self._llm.complete(
            CHAT_NARRATE_SYSTEM,
            CHAT_NARRATE_USER.format(
                question=question,
                result=f"{result.row_count} row(s) returned. First rows: {preview}",
            ),
        )
        text = text.strip() if text else ""

        # Single-value answers (avg/count/sum/min/max): the LLM must NOT invent
        # the figure. Trust its phrasing only if its numbers match the real
        # computed values; otherwise state the exact value deterministically.
        if result.row_count == 1:
            truth = [float(v) for v in result.rows[0].values() if self._is_number(v)]
            if text and self._numbers_agree(text, truth):
                return text
            return self._narrate_exact(result)

        # Multi-row answers were previously unguarded: the model saw ten rows and
        # confidently reported counts drawn from the preview. Any number it
        # states must be traceable to the actual result.
        if text and self._numbers_are_grounded(text, result):
            return text
        return self._fallback_narrate(result)

    @classmethod
    def _numbers_are_grounded(cls, text: str, result: QueryResult) -> bool:
        """True if every number in ``text`` exists in the result or its size.

        Values are checked against the whole result set, not the preview the
        model was shown, so "there are 4 customers" fails when 87 rows came
        back. Small integers are allowed through only when they match the row
        count, so a preview length can never masquerade as a total.
        """
        stated = cls._stated_numbers(text)
        if not stated:
            return True

        allowed: set[float] = {float(result.row_count), float(len(result.columns))}
        for row in result.rows:
            for value in row.values():
                if cls._is_number(value):
                    allowed.add(float(value))

        # Every figure must be a faithful rounding of something in the result —
        # a percentage tolerance would let altered cents through.
        return all(
            any(cls._is_faithful(value, decimals, a) for a in allowed)
            for value, decimals in stated
        )

    @staticmethod
    def _is_number(v) -> bool:
        try:
            float(v)
            return True
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _stated_numbers(text: str) -> list[tuple[float, int]]:
        """Numbers written in ``text`` as ``(value, decimals_shown)`` pairs.

        The decimal count matters: it says how precisely the writer claimed to
        quote the figure, which is what makes a rounding check possible.
        """
        out: list[tuple[float, int]] = []
        for token in re.findall(r"-?\d[\d,]*(?:\.\d+)?", text):
            cleaned = token.replace(",", "")
            decimals = len(cleaned.split(".")[1]) if "." in cleaned else 0
            try:
                out.append((float(cleaned), decimals))
            except ValueError:  # pragma: no cover - regex guarantees a number
                continue
        return out

    @staticmethod
    def _is_faithful(stated: float, decimals: int, truth: float) -> bool:
        """Whether ``stated`` is a legitimate rounding of ``truth``.

        A percentage tolerance is the wrong test: 7,946.16 is within 2% of
        7,945.76 yet states different cents, which reads as a precise figure the
        data never produced. Instead the claim must survive rounding to the
        precision it was written at — 7,946 and 7,945.76 both pass, 7,946.16
        does not.
        """
        if abs(truth) < 1e-9:
            return abs(stated) < 1e-6
        # Allow the stated precision, and one digit either side of it, so
        # "7,945.8" (1dp) and "7,945.762" (3dp) are both accepted.
        for places in {max(decimals - 1, 0), decimals, decimals + 1}:
            if round(stated, places) == round(truth, places):
                return True
        return False

    @classmethod
    def _numbers_agree(cls, text: str, truth: list[float]) -> bool:
        """True if every computed value is faithfully quoted in ``text``.

        Guards against hallucinated figures: a rounded "$3,954" for 3953.85
        passes; "$1,791" or "$3,954.12" for the same value does not.
        """
        if not truth:
            return True
        stated = cls._stated_numbers(text)
        if not stated:
            return False
        return all(
            any(cls._is_faithful(value, decimals, t) for value, decimals in stated)
            for t in truth
        )

    @classmethod
    def _narrate_exact(cls, result: QueryResult) -> str:
        """Deterministic sentence with the EXACT computed value(s)."""
        row = result.rows[0]
        _labels = {"avg": "average", "sum": "total", "min": "minimum", "max": "maximum",
                   "count": "count", "row_count": "row count", "total": "total"}

        def fmt(v) -> str:
            if not cls._is_number(v):
                return "no value" if v is None else str(v)
            n = float(v)
            return f"{n:,.0f}" if n.is_integer() else f"{n:,.2f}"

        def humanize(k: str) -> str:
            # DuckDB names bare aggregates like `count_star()`; strip the call
            # syntax so the sentence doesn't read "The count star() is 42".
            kl = re.sub(r"\(\s*\**\s*\)", "", k.lower()).strip()
            if kl in {"count_star", "countstar"}:
                return "count"
            for pre, word in _labels.items():
                if kl == pre or kl.startswith(pre + "_"):
                    rest = kl[len(pre):].strip("_").replace("_", " ")
                    return f"{word} {rest}".strip()
            return kl.replace("_", " ")

        parts = [(humanize(k), fmt(v)) for k, v in row.items()]
        if len(parts) == 1:
            return f"The {parts[0][0]} is {parts[0][1]}."
        return "Here's the result — " + ", ".join(f"{lbl}: {val}" for lbl, val in parts) + "."

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
            if not data:
                return None
            return {
                "type": "scatter", "title": f"{a} vs {b}", "x": "x", "y": "y",
                "x_label": self._axis_label(a), "y_label": self._axis_label(b), "data": data,
            }

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
        y_label = self._axis_label(measure)
        return {
            "type": chart_type, "title": f"{y_label} by {cat}",
            "x": "name", "y": "value",
            "x_label": cat, "y_label": y_label, "data": data,
        }

    # SQL aliases that reveal the aggregation behind a column.
    _AGG_PREFIXES = (
        ("sum_", "Total "), ("total_", "Total "), ("avg_", "Average "), ("mean_", "Average "),
        ("max_", "Maximum "), ("min_", "Minimum "), ("count_", "Count of "),
    )

    @classmethod
    def _axis_label(cls, column: str) -> str:
        """Readable axis caption for a SQL result column.

        Query aliases carry the aggregation (``sum_revenue``, ``avg_price``);
        spelling it out is what tells the reader whether a bar is a total or an
        average. Without this the axis just said "sum_revenue" — or worse,
        "revenue", which reads as a raw value.
        """
        name = re.sub(r"\(\s*\**\s*\)", "", str(column)).strip()
        lowered = name.lower()
        if lowered in {"count", "count_star", "n", "rows", "row_count", "num_rows"}:
            return "Number of rows"
        for prefix, word in cls._AGG_PREFIXES:
            if lowered.startswith(prefix):
                rest = name[len(prefix):].replace("_", " ").strip()
                return f"{word}{rest}" if rest else word.strip()
        return name.replace("_", " ")

    # ---- query frame -------------------------------------------------- #
    def _query_frame(self, ctx: AgentContext) -> tuple[pd.DataFrame, list[str]]:
        """The frame SQL runs against, with date columns made comparable.

        Uploaded date columns routinely mix formats (``15/02/2024`` beside
        ``2024-04-10``). DuckDB's ``TRY_CAST`` parses only one of them and turns
        the rest into NULL, so a month filter silently matches nothing. Parsing
        them the same way the charts do makes date comparisons work on any
        dataset, whatever format the file used.

        Returns the frame plus notes about values that could not be parsed.
        """
        if ctx.profile is None:
            return ctx.df, []

        date_columns = [
            c.name for c in ctx.profile.columns
            if c.semantic_type in _TEMPORAL and c.name in ctx.df.columns
        ]
        if not date_columns:
            return ctx.df, []

        frame = ctx.df.copy()
        notes: list[str] = []
        for name in date_columns:
            if pd.api.types.is_datetime64_any_dtype(frame[name]):
                continue
            parsed = parse_dates(frame[name])
            unparsed = int(parsed.isna().sum() - frame[name].isna().sum())
            frame[name] = parsed
            if unparsed > 0:
                notes.append(
                    f"{unparsed} of {len(frame)} '{name}' values aren't recognisable dates "
                    "and are excluded from any date filter."
                )
        return frame, notes

    @staticmethod
    def _text_columns(ctx: AgentContext) -> set[str]:
        """Columns whose values are free text, from the profile when available."""
        if ctx.profile is not None:
            return {c.name for c in ctx.profile.columns if c.semantic_type in _TEXTUAL}
        return {c for c in ctx.df.columns if ctx.df[c].dtype == object}

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
