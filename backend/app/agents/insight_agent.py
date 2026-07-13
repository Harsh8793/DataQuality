"""Insight agent: LLM-narrated issue explanations and business insights."""

from __future__ import annotations

import json

from app.agents.base import Agent, AgentContext, AgentResult
from app.core.engines.quality_checks import QualityFinding
from app.core.llm import get_llm
from app.core.llm.prompts import (
    EXPLAIN_ISSUES_SYSTEM,
    EXPLAIN_ISSUES_USER,
    INSIGHTS_SYSTEM,
    INSIGHTS_USER,
)

# Deterministic fallbacks so issues are always explained, even without the LLM.
_FALLBACK = {
    "missing_values": ("Missing values present", "Data was not captured or lost in transfer.",
                       "Incomplete records reduce reporting accuracy.", "Impute or collect the missing data."),
    "blank_strings": ("Blank text values", "Fields were submitted empty or whitespace-only.",
                      "Blanks hide as 'filled' values and skew completeness metrics.",
                      "Convert blanks to null, then fill or collect real values."),
    "whitespace": ("Untrimmed whitespace", "Values carry leading/trailing spaces from manual entry or exports.",
                   "Identical values fail to match in joins, filters and group-bys.",
                   "Trim whitespace from the affected values."),
    "duplicate_rows": ("Duplicate rows detected", "Records were ingested more than once.",
                       "Duplicates inflate counts and skew metrics.", "Deduplicate on a unique key."),
    "duplicate_ids": ("Duplicate identifiers", "The same ID appears on multiple rows.",
                      "Lookups and joins return multiple matches, corrupting downstream reports.",
                      "Keep one row per ID or assign new unique IDs."),
    "invalid_email": ("Invalid email addresses", "Free-text entry without validation.",
                      "Undeliverable communications and bounce costs.", "Validate and correct email formats."),
    "invalid_phone": ("Invalid phone numbers", "Numbers entered without a consistent format check.",
                      "Failed calls/SMS and wasted outreach effort.", "Standardize and validate phone formats."),
    "invalid_url": ("Invalid URLs", "Links entered or migrated incorrectly.",
                    "Broken references in reports and applications.", "Validate and repair the URLs."),
    "invalid_date": ("Invalid dates", "Dates entered in mixed or impossible formats.",
                     "Time-based analysis (trends, ageing) becomes unreliable.",
                     "Parse to a single date format; quarantine unparseable values."),
    "negative_values": ("Unexpected negative values", "Sign errors or refunds mixed into a positive-only field.",
                        "Totals and averages are silently understated.",
                        "Confirm whether negatives are valid; quarantine or correct them."),
    "outliers": ("Statistical outliers", "Values far outside the typical range (data-entry errors or genuine extremes).",
                 "A handful of extremes can distort averages and charts.",
                 "Verify extremes; cap or exclude confirmed errors."),
    "case_inconsistency": ("Inconsistent casing", "The same value appears in different capitalizations.",
                           "'east' and 'East' are counted as different groups.",
                           "Standardize to one canonical casing."),
    "mixed_types": ("Mixed data types", "Numbers and text are mixed in one column.",
                    "The column can't be aggregated or sorted reliably.",
                    "Convert to the majority type; quarantine the rest."),
    "constant_column": ("Constant column", "Every row holds the same value.",
                        "The column adds no analytical value and wastes attention.",
                        "Drop the column or verify the feed that populates it."),
    "duplicate_columns": ("Duplicate columns", "Two columns contain identical data.",
                          "Redundant storage and ambiguous joins.", "Drop one of the duplicates."),
    "high_cardinality": ("Very high cardinality", "Nearly every value is unique (free text or IDs).",
                         "Unsuitable for grouping; may hide PII.", "Confirm the column's role; exclude from breakdowns."),
    "low_cardinality": ("Very low variety", "The column has only a couple of distinct values.",
                        "Limited analytical signal.", "Confirm this is expected for the field."),
    "unicode_issues": ("Corrupted characters", "Encoding mismatches during export/import.",
                       "Garbled text in reports and failed matching.", "Re-import with the correct encoding."),
    "empty_dataset": ("Empty dataset", "The file contained headers but no rows.",
                      "Nothing to analyze.", "Upload a file with data rows."),
    "datatype_mismatch": ("Declared/actual type mismatch", "Values don't match the column's expected type.",
                          "Type casts fail or silently corrupt values downstream.",
                          "Convert the column to its correct type."),
}


class InsightAgent(Agent):
    """Generates AI explanations for issues and business-level insights."""

    name = "insight"

    def __init__(self) -> None:
        super().__init__()
        self._llm = get_llm()

    def explain_issues(self, ctx: AgentContext) -> dict[str, dict]:
        """Return a map of ``check_key -> explanation`` for the findings."""
        findings = ctx.findings
        if not findings:
            return {}
        payload = [
            {"check_key": f.check_key, "column": f.column_name, "severity": f.severity, "count": f.count}
            for f in findings[:15]
        ]
        explanations = self._llm_explanations(ctx, payload)
        # Merge LLM output with deterministic fallbacks by check_key.
        result: dict[str, dict] = {}
        for f in findings:
            result[f.check_key] = explanations.get(f.check_key) or self._fallback(f)
        return result

    def generate_insights(self, ctx: AgentContext) -> list[dict]:
        """Return a list of business insights (LLM, with a safe fallback)."""
        if not self._llm.available or ctx.profile is None:
            return self._fallback_insights(ctx)
        profile_summary = {
            "rows": ctx.profile.row_count,
            "columns": [{"name": c.name, "type": c.semantic_type} for c in ctx.profile.columns[:15]],
        }
        quality_summary = {"score": ctx.score.overall if ctx.score else None,
                           "issues": len(ctx.findings)}
        raw = self._llm.complete_json(
            INSIGHTS_SYSTEM,
            INSIGHTS_USER.format(
                dataset_name=ctx.dataset_name,
                profile=json.dumps(profile_summary),
                quality=json.dumps(quality_summary),
            ),
        )
        return raw if isinstance(raw, list) else self._fallback_insights(ctx)

    def run(self, ctx: AgentContext) -> AgentResult:
        """Explain issues and generate insights; store both on the context."""
        ctx.emit("progress", {"agent": self.name, "status": "running"})
        explanations = self.explain_issues(ctx)
        insights = self.generate_insights(ctx)
        ctx.meta["explanations"] = explanations
        ctx.meta["insights"] = insights
        ctx.emit("progress", {"agent": self.name, "status": "done", "summary": "AI insights ready"})
        return self._ok({"explanations": explanations, "insights": insights})

    # ---- helpers ------------------------------------------------------ #
    def _llm_explanations(self, ctx: AgentContext, payload: list[dict]) -> dict[str, dict]:
        if not self._llm.available:
            return {}
        raw = self._llm.complete_json(
            EXPLAIN_ISSUES_SYSTEM,
            EXPLAIN_ISSUES_USER.format(
                dataset_name=ctx.dataset_name,
                row_count=ctx.profile.row_count if ctx.profile else 0,
                col_count=ctx.profile.col_count if ctx.profile else 0,
                issues=json.dumps(payload),
            ),
        )
        if not isinstance(raw, list):
            return {}
        return {item.get("check_key"): item for item in raw if isinstance(item, dict) and item.get("check_key")}

    def _fallback(self, f: QualityFinding) -> dict:
        problem, why, impact, fix = _FALLBACK.get(
            f.check_key,
            (f"{f.check_key.replace('_', ' ').title()} detected",
             "Detected by deterministic rules.",
             "May reduce data trustworthiness.",
             "Review and remediate the affected column."),
        )
        return {
            "check_key": f.check_key, "problem": problem, "why": why,
            "business_impact": impact, "recommended_fix": fix, "confidence": 0.6,
        }

    def _fallback_insights(self, ctx: AgentContext) -> list[dict]:
        """Data-driven insights computed without the LLM."""
        score = ctx.score.overall if ctx.score else 0
        insights = [{
            "title": "Overall data health",
            "insight": f"The dataset scores {score}/100 across six quality dimensions."
            if ctx.score else "The dataset has not been quality-scored yet.",
            "action": "Run one-click cleaning to raise the score before analytics.",
            "category": "risk" if score < 70 else "opportunity",
        }]
        if ctx.profile is None:
            return insights

        # Completeness: call out the emptiest column if it's material.
        worst = max(ctx.profile.columns, key=lambda c: c.null_pct, default=None)
        if worst is not None and worst.null_pct >= 5:
            insights.append({
                "title": f"Completeness gap in {worst.name}",
                "insight": f"'{worst.name}' is {worst.null_pct}% empty — the biggest gap "
                f"across {ctx.profile.col_count} columns.",
                "action": "Confirm whether this field is expected to be sparse, or fix the source feed.",
                "category": "risk",
            })

        # Spread of the primary numeric measure.
        numeric = [c for c in ctx.profile.columns
                   if c.semantic_type in {"numeric", "integer", "currency"} and c.mean_val is not None]
        if numeric:
            c = numeric[0]
            insights.append({
                "title": f"Range of {c.name}",
                "insight": f"'{c.name}' spans {c.min_val} to {c.max_val} with an average of "
                f"{round(c.mean_val, 2)} across {ctx.profile.row_count:,} rows.",
                "action": "Check whether the extremes are genuine or data-entry outliers.",
                "category": "trend",
            })

        # Concentration: low-cardinality categorical worth grouping by.
        cats = [c for c in ctx.profile.columns
                if c.semantic_type in {"categorical", "text"} and 1 < c.distinct_count <= 15]
        if cats:
            c = cats[0]
            insights.append({
                "title": f"Natural grouping by {c.name}",
                "insight": f"'{c.name}' has only {c.distinct_count} distinct values — a natural "
                "dimension for breakdowns and dashboards.",
                "action": f"Ask the chat for totals or averages by {c.name}.",
                "category": "opportunity",
            })
        return insights
