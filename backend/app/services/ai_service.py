"""AI playground service: explain widgets, data stories, comparisons, suggestions.

Every LLM call here has a deterministic fallback so the features keep working
when the model is unavailable or the token budget is exhausted.
"""

from __future__ import annotations

import json

import pandas as pd
from sqlalchemy.orm import Session

from app.agents.profiling_agent import ProfilingAgent
from app.constants.enums import SemanticType
from app.core.llm import prompts
from app.core.llm.groq_client import get_llm
from app.repositories.analysis_repository import QualityReportRepository
from app.repositories.dataset_repository import DatasetRepository
from app.schemas.ai import (
    ColumnShift,
    CompareResponse,
    ExplainRequest,
    ExplainResponse,
    StoryResponse,
    SuggestionsResponse,
)
from app.services.base import BaseService, DatasetContextMixin

_NUMERIC = {SemanticType.NUMERIC, SemanticType.INTEGER, SemanticType.CURRENCY}
_CATEGORICAL = {SemanticType.CATEGORICAL, SemanticType.TEXT, SemanticType.BOOLEAN}
_TEMPORAL = {SemanticType.DATE, SemanticType.DATETIME}


class AiService(BaseService, DatasetContextMixin):
    """Cross-cutting AI features that make the data explorable."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.datasets = DatasetRepository(db)
        self.reports = QualityReportRepository(db)
        self.profiling_agent = ProfilingAgent()
        self.llm = get_llm()

    # ---- "Explain this" ------------------------------------------------ #
    def explain_widget(self, dataset_id: int, user_id: int, req: ExplainRequest) -> ExplainResponse:
        """Explain a KPI or chart in plain business language."""
        dataset = self._load_owned_dataset(dataset_id, user_id)

        widget = {"kind": req.kind, "label": req.label}
        if req.kind == "kpi":
            widget["value"] = req.value
            widget["format"] = req.format
        else:
            widget["chart_type"] = req.chart_type
            widget["x_axis"] = req.x
            widget["y_axis"] = req.y
            widget["data_sample"] = req.data[:12]

        text = self.llm.complete(
            prompts.EXPLAIN_WIDGET_SYSTEM,
            prompts.EXPLAIN_WIDGET_USER.format(
                dataset_name=dataset.name, row_count=dataset.row_count,
                col_count=dataset.col_count, widget=json.dumps(widget, default=str),
            ),
        )
        if text:
            return ExplainResponse(explanation=text.strip(), generated_by="ai")
        return ExplainResponse(explanation=self._fallback_explain(req), generated_by="fallback")

    @staticmethod
    def _fallback_explain(req: ExplainRequest) -> str:
        if req.kind == "kpi":
            return (
                f'"{req.label}" is a single summary number computed across every row of this dataset '
                f"(current value: {req.value}). Use it as a quick health check — if it moves "
                "unexpectedly between uploads, the underlying data has changed and is worth investigating."
            )
        points = [d for d in req.data if isinstance(d.get("value"), (int, float))]
        extra = ""
        if points:
            top = max(points, key=lambda d: d["value"])
            low = min(points, key=lambda d: d["value"])
            extra = (
                f' The largest segment is "{top.get("name")}" ({top["value"]}) and the smallest is '
                f'"{low.get("name")}" ({low["value"]}).'
            )
        return (
            f'"{req.label}" is a {req.chart_type or "summary"} chart showing {req.y or "values"} '
            f"across {req.x or 'categories'} in your data.{extra} Look for segments that dominate "
            "or lag far behind the rest — those are usually where the story is."
        )

    # ---- Data story ------------------------------------------------------ #
    def get_story(self, dataset_id: int, user_id: int, refresh: bool = False) -> StoryResponse:
        """Return the cached executive summary, generating it on first request."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        if dataset.story and not refresh:
            return StoryResponse(story=dataset.story, generated_by="cached")

        ctx = self._build_context(dataset)
        self.profiling_agent.run(ctx)
        profile = ctx.profile
        assert profile is not None

        report = self.reports.latest_for_dataset(dataset_id)
        quality = (
            f"quality score {report.overall_score}/100, {report.total_issues} issues, "
            f"{report.duplicate_rows} duplicate rows" if report else "not analyzed yet"
        )
        profile_summary = {
            "rows": profile.row_count, "columns": profile.col_count,
            "columns_detail": [
                {"name": c.name, "type": c.semantic_type, "null_pct": c.null_pct,
                 "distinct": c.distinct_count}
                for c in profile.columns[:20]
            ],
        }
        text = self.llm.complete(
            prompts.DATA_STORY_SYSTEM,
            prompts.DATA_STORY_USER.format(
                dataset_name=dataset.name,
                profile=json.dumps(profile_summary, default=str),
                quality=quality,
            ),
        )
        generated_by = "ai"
        if not text:
            text = self._fallback_story(dataset, profile, report)
            generated_by = "fallback"

        self.datasets.update(dataset, story=text.strip())
        self.db.commit()
        return StoryResponse(story=text.strip(), generated_by=generated_by)

    @staticmethod
    def _fallback_story(dataset, profile, report) -> str:
        numeric = [c.name for c in profile.columns if c.semantic_type in _NUMERIC]
        worst = sorted(profile.columns, key=lambda c: -c.null_pct)[:2]
        parts = [
            f'"{dataset.name}" contains {profile.row_count:,} rows across {profile.col_count} columns.'
        ]
        if numeric:
            parts.append(f"Key measures include {', '.join(numeric[:3])}.")
        gaps = [f"{c.name} ({c.null_pct}% missing)" for c in worst if c.null_pct > 5]
        if gaps:
            parts.append(f"The biggest completeness gaps are {' and '.join(gaps)}.")
        if report:
            parts.append(
                f"The latest quality analysis scored it {report.overall_score}/100 with "
                f"{report.total_issues} detected issues."
            )
        return " ".join(parts)

    # ---- Dataset comparison ----------------------------------------------- #
    def compare(self, left_id: int, right_id: int, user_id: int) -> CompareResponse:
        """Diff two datasets (schema + distribution shifts) and narrate it."""
        left = self._load_owned_dataset(left_id, user_id)
        right = self._load_owned_dataset(right_id, user_id)
        ldf, rdf = self._read_frame(left), self._read_frame(right)

        lcols, rcols = set(ldf.columns), set(rdf.columns)
        added = sorted(rcols - lcols)
        removed = sorted(lcols - rcols)
        common = sorted(lcols & rcols)

        shifts: list[ColumnShift] = []
        for col in common:
            ls, rs = ldf[col], rdf[col]
            lnull = round(float(ls.isna().mean() * 100), 2)
            rnull = round(float(rs.isna().mean() * 100), 2)
            lnum = pd.to_numeric(ls, errors="coerce")
            rnum = pd.to_numeric(rs, errors="coerce")
            if lnum.notna().sum() >= 3 and rnum.notna().sum() >= 3:
                lmean, rmean = float(lnum.mean()), float(rnum.mean())
                change = round((rmean - lmean) / abs(lmean) * 100, 1) if lmean else None
                shifts.append(ColumnShift(
                    column=col, left_mean=round(lmean, 2), right_mean=round(rmean, 2),
                    mean_change_pct=change, left_null_pct=lnull, right_null_pct=rnull,
                ))
            elif abs(lnull - rnull) >= 1:
                shifts.append(ColumnShift(column=col, left_null_pct=lnull, right_null_pct=rnull))

        # Most-moved columns first; keep the payload/prompt small.
        shifts.sort(key=lambda s: -(abs(s.mean_change_pct or 0) + abs(s.right_null_pct - s.left_null_pct)))
        shifts = shifts[:8]

        diff = {
            "row_delta": len(rdf) - len(ldf),
            "added_columns": added, "removed_columns": removed,
            "shifts": [s.model_dump() for s in shifts],
        }
        narrative = self.llm.complete(
            prompts.COMPARE_SYSTEM,
            prompts.COMPARE_USER.format(
                left_name=left.name, left_rows=len(ldf), left_cols=ldf.shape[1],
                right_name=right.name, right_rows=len(rdf), right_cols=rdf.shape[1],
                diff=json.dumps(diff, default=str),
            ),
        )
        generated_by = "ai"
        if not narrative:
            narrative = self._fallback_compare(left.name, right.name, ldf, rdf, added, removed, shifts)
            generated_by = "fallback"

        return CompareResponse(
            left_name=left.name, right_name=right.name,
            left_rows=len(ldf), right_rows=len(rdf),
            left_cols=ldf.shape[1], right_cols=rdf.shape[1],
            added_columns=added, removed_columns=removed, common_columns=len(common),
            column_shifts=shifts, narrative=narrative.strip(), generated_by=generated_by,
        )

    @staticmethod
    def _fallback_compare(lname, rname, ldf, rdf, added, removed, shifts) -> str:
        parts = [
            f'"{rname}" has {len(rdf):,} rows vs {len(ldf):,} in "{lname}" '
            f"({len(rdf) - len(ldf):+,} rows)."
        ]
        if added:
            parts.append(f"New columns: {', '.join(added[:5])}.")
        if removed:
            parts.append(f"Removed columns: {', '.join(removed[:5])}.")
        moved = [s for s in shifts if s.mean_change_pct is not None and abs(s.mean_change_pct) >= 1]
        if moved:
            top = moved[0]
            parts.append(
                f"The biggest shift is {top.column}: average moved from {top.left_mean} to "
                f"{top.right_mean} ({top.mean_change_pct:+.1f}%)."
            )
        if not (added or removed or moved):
            parts.append("The schemas match and no material distribution shifts were detected.")
        return " ".join(parts)

    # ---- Starter questions (deterministic — zero tokens) ------------------- #
    def chat_suggestions(self, dataset_id: int, user_id: int) -> SuggestionsResponse:
        """Generate clickable starter questions from the dataset's own columns."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        ctx = self._build_context(dataset)
        self.profiling_agent.run(ctx)
        profile = ctx.profile
        assert profile is not None

        numeric = [c for c in profile.columns if c.semantic_type in _NUMERIC]
        categorical = [
            c for c in profile.columns
            if c.semantic_type in _CATEGORICAL and 1 < c.distinct_count <= 25
        ]
        temporal = [c for c in profile.columns if c.semantic_type in _TEMPORAL]

        questions: list[str] = []
        if numeric and categorical:
            questions.append(f"What is the average {numeric[0].name} by {categorical[0].name}?")
            questions.append(f"Top 5 {categorical[0].name} by total {numeric[0].name}")
        if categorical:
            cat = categorical[1] if len(categorical) > 1 else categorical[0]
            questions.append(f"How many rows are there per {cat.name}?")
        if temporal and numeric:
            questions.append(f"Show the trend of {numeric[0].name} over {temporal[0].name}")
        if len(numeric) >= 2:
            questions.append(f"Is there a relationship between {numeric[0].name} and {numeric[1].name}?")
        if numeric and not questions:
            questions.append(f"What are the min, max and average of {numeric[0].name}?")
        if not questions:
            questions.append("How many rows does this dataset have?")
            questions.append("Which columns have missing values?")
        return SuggestionsResponse(questions=questions[:4])
