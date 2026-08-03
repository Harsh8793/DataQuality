"""Governance, Edit data and Reports tabs.

Covers ``agents/governance_agent.py``, the cell-coercion core of
``services/edit_service.py`` and the report writers in
``services/report_service.py``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.agents.base import AgentContext
from app.agents.governance_agent import GovernanceAgent
from app.constants.enums import Classification, IngestionTier
from app.core.engines.profiler import Profiler
from app.core.engines.scorer import QualityScore
from app.exceptions.base import BadRequestException
from app.services.edit_service import EditService, _jsonable
from app.services.report_service import ReportService

from tests.conftest import scripted_llm


def context_for(frame: pd.DataFrame, *, score: float | None = None) -> AgentContext:
    ctx = AgentContext(dataset_id=1, dataset_name="demo", df=frame)
    ctx.profile = Profiler().profile(frame)
    if score is not None:
        ctx.score = QualityScore(
            overall=score,
            dimensions={"completeness": score, "accuracy": score, "consistency": score,
                        "uniqueness": score, "validity": score, "integrity": score},
            duplicate_rows=0,
            total_issues=0,
        )
    return ctx


# --------------------------------------------------------------------------- #
# Governance tab
# --------------------------------------------------------------------------- #
class TestGovernanceClassification:
    def test_flags_pii_from_semantic_type(self) -> None:
        frame = pd.DataFrame({"email": ["a@x.com", "b@x.com"], "n": [1, 2]})
        result = GovernanceAgent().classify(context_for(frame))
        assert "email" in result.pii_columns
        assert result.classification == Classification.PII

    def test_flags_pii_from_column_naming(self) -> None:
        frame = pd.DataFrame({"customer_name": ["Ann", "Bob"], "n": [1, 2]})
        result = GovernanceAgent().classify(context_for(frame))
        assert "customer_name" in result.pii_columns

    def test_financial_data_without_pii(self) -> None:
        frame = pd.DataFrame({"revenue": [1.0, 2.0], "widgets": [1, 2]})
        result = GovernanceAgent().classify(context_for(frame))
        assert result.classification == Classification.FINANCIAL

    def test_healthcare_outranks_other_signals(self) -> None:
        frame = pd.DataFrame({"diagnosis": ["a", "b"], "email": ["a@x.com", "b@x.com"]})
        result = GovernanceAgent().classify(context_for(frame))
        assert result.classification == Classification.HEALTHCARE

    def test_plain_data_is_internal(self) -> None:
        frame = pd.DataFrame({"widget": ["a", "b"], "count_of": [1, 2]})
        result = GovernanceAgent().classify(context_for(frame))
        assert result.classification == Classification.INTERNAL

    @pytest.mark.parametrize(
        ("score", "cleaned", "tier"),
        [
            (95.0, True, IngestionTier.GOLD),
            (95.0, False, IngestionTier.SILVER),
            (80.0, False, IngestionTier.SILVER),
            (40.0, False, IngestionTier.BRONZE),
        ],
    )
    def test_tier_follows_score_and_cleaning(self, score: float, cleaned: bool, tier: str) -> None:
        ctx = context_for(pd.DataFrame({"a": [1, 2]}), score=score)
        ctx.meta["is_cleaned"] = cleaned
        assert GovernanceAgent().classify(ctx).ingestion_tier == tier

    def test_requires_a_profile(self) -> None:
        ctx = AgentContext(dataset_id=1, dataset_name="d", df=pd.DataFrame({"a": [1]}))
        with pytest.raises(ValueError, match="Profile is required"):
            GovernanceAgent().classify(ctx)

    def test_rule_metadata_covers_every_column(self) -> None:
        frame = pd.DataFrame({"email": ["a@x.com"], "amount": [1.0], "note": ["x"]})
        result = GovernanceAgent().classify(context_for(frame))
        assert {m["name"] for m in result.column_metadata} == set(frame.columns)
        assert all(m["business_name"] and m["description"] for m in result.column_metadata)

    def test_metadata_marks_pii_sensitivity(self) -> None:
        frame = pd.DataFrame({"email": ["a@x.com"], "n": [1]})
        result = GovernanceAgent().classify(context_for(frame))
        email_meta = next(m for m in result.column_metadata if m["name"] == "email")
        assert email_meta["is_pii"] is True
        assert email_meta["sensitivity"] == "pii"

    def test_run_stores_the_result_on_the_context(self) -> None:
        ctx = context_for(pd.DataFrame({"a": [1, 2]}))
        assert GovernanceAgent().run(ctx).ok is True
        assert ctx.meta["governance"].classification


class TestGovernanceLlmEnrichment:
    """Wide tables are batched; the rules stay authoritative throughout."""

    def _wide_frame(self, columns: int) -> pd.DataFrame:
        return pd.DataFrame({f"col_{i:03d}": [i, i + 1] for i in range(columns)})

    def test_no_llm_keeps_deterministic_metadata(self) -> None:
        frame = self._wide_frame(3)
        result = GovernanceAgent().classify(context_for(frame))
        assert all(m["description"].endswith("column") for m in result.column_metadata)

    def test_all_columns_are_described_across_batches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: columns past the old cap kept a generic description."""
        columns = GovernanceAgent.COLUMN_BATCH * 2 + 5
        frame = self._wide_frame(columns)

        class BatchingLLM:
            available = True

            def complete_json(self, system: str, user: str):
                import json as _json
                import re as _re

                names = _re.findall(r'"name":\s*"([^"]+)"', user)
                return {
                    "rationale": "ok",
                    "columns": [
                        {"name": n, "business_name": n.title(), "description": f"Described {n}."}
                        for n in names
                    ],
                }

            def complete(self, *a, **k):
                return None

        stub = BatchingLLM()
        monkeypatch.setattr("app.agents.governance_agent.get_llm", lambda: stub)
        agent = GovernanceAgent()
        agent._llm = stub

        result = agent.classify(context_for(frame))
        described = [m for m in result.column_metadata if m["description"].startswith("Described")]
        assert len(described) == columns

    def test_a_failing_batch_is_split_and_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []

        class FlakyLLM:
            available = True

            def complete_json(self, system: str, user: str):
                import re as _re

                names = _re.findall(r'"name":\s*"([^"]+)"', user)
                calls.append(len(names))
                if len(names) > 5:  # pretend the response was truncated
                    return None
                return {
                    "rationale": "",
                    "columns": [
                        {"name": n, "business_name": n, "description": f"Described {n}."}
                        for n in names
                    ],
                }

            def complete(self, *a, **k):
                return None

        stub = FlakyLLM()
        monkeypatch.setattr("app.agents.governance_agent.get_llm", lambda: stub)
        agent = GovernanceAgent()
        agent._llm = stub

        result = agent.classify(context_for(self._wide_frame(8)))
        assert len(calls) > 1, "a failed batch must be retried in halves"
        assert any(m["description"].startswith("Described") for m in result.column_metadata)

    def test_llm_can_never_change_pii_flags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The model is unreliable at PII, so rules stay authoritative."""
        frame = pd.DataFrame({"email": ["a@x.com", "b@x.com"]})
        stub = scripted_llm(
            monkeypatch,
            payload={
                "rationale": "nothing sensitive here",
                "columns": [
                    {"name": "email", "business_name": "Email", "description": "An email.",
                     "is_pii": False, "sensitivity": "public"}
                ],
            },
        )
        agent = GovernanceAgent()
        agent._llm = stub
        result = agent.classify(context_for(frame))
        email_meta = next(m for m in result.column_metadata if m["name"] == "email")
        assert email_meta["is_pii"] is True
        assert result.classification == Classification.PII

    def test_unparseable_response_falls_back_to_rules(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = scripted_llm(monkeypatch, payload=None)
        agent = GovernanceAgent()
        agent._llm = stub
        result = agent.classify(context_for(pd.DataFrame({"a": [1, 2]})))
        assert result.column_metadata[0]["description"].endswith("column")


# --------------------------------------------------------------------------- #
# Edit data tab
# --------------------------------------------------------------------------- #
class TestCellCoercion:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, None),
            (float("nan"), None),
            (np.int64(5), 5),
            (np.float64(1.5), 1.5),
            (np.bool_(True), True),
            ("text", "text"),
        ],
    )
    def test_values_become_json_safe(self, value, expected) -> None:
        assert _jsonable(value) == expected

    def test_timestamps_become_strings(self) -> None:
        assert isinstance(_jsonable(pd.Timestamp("2024-01-05")), str)

    def test_numeric_cell_accepts_a_numeric_string(self) -> None:
        frame = pd.DataFrame({"v": [1.0, 2.0]})
        updated = EditService._assign(frame, 0, "v", "9.5")
        assert updated.at[0, "v"] == 9.5

    def test_numeric_cell_rejects_non_numeric_text(self) -> None:
        frame = pd.DataFrame({"v": [1.0, 2.0]})
        with pytest.raises(BadRequestException):
            EditService._assign(frame, 0, "v", "abc")

    def test_blank_clears_a_numeric_cell_to_null(self) -> None:
        frame = pd.DataFrame({"v": [1.0, 2.0]})
        updated = EditService._assign(frame, 0, "v", "   ")
        assert pd.isna(updated.at[0, "v"])

    def test_text_cell_accepts_any_string(self) -> None:
        frame = pd.DataFrame({"c": ["a", "b"]})
        assert EditService._assign(frame, 1, "c", "z").at[1, "c"] == "z"

    def test_assignment_leaves_other_rows_untouched(self) -> None:
        frame = pd.DataFrame({"v": [1.0, 2.0, 3.0]})
        updated = EditService._assign(frame, 1, "v", "9")
        assert updated["v"].tolist() == [1.0, 9.0, 3.0]


# --------------------------------------------------------------------------- #
# Reports tab
# --------------------------------------------------------------------------- #
class TestReportWriters:
    @pytest.fixture
    def payload(self) -> dict:
        return {
            "dataset": {"id": 1, "name": "demo", "rows": 100, "columns": 5},
            "scores": {"overall": 82.5, "completeness": 90.0, "accuracy": 80.0,
                       "consistency": 75.0, "uniqueness": 88.0, "validity": 79.0,
                       "integrity": 83.0},
            "summary": {"total_issues": 4, "duplicate_rows": 2},
            "issues": [
                {"check": "missing_values", "column": "revenue", "severity": "high",
                 "count": 12, "fix": "Impute revenue."},
                {"check": "duplicate_rows", "column": None, "severity": "medium",
                 "count": 2, "fix": "Drop duplicates."},
            ],
            "profile": [],
            "dashboard": {"kpis": [], "charts": []},
        }

    @pytest.mark.parametrize(
        ("value", "fmt", "expected"),
        [
            (1234.0, None, "1,234"),
            (1234.5, None, "1,234.50"),
            (1234.0, "currency", "$1,234"),
            ("n/a", None, "n/a"),
            (None, None, "None"),
        ],
    )
    def test_kpi_values_are_human_formatted(self, value, fmt, expected) -> None:
        assert ReportService._fmt_value(value, fmt) == expected

    def test_csv_report_lists_every_issue(self, tmp_path: Path, payload: dict) -> None:
        path = tmp_path / "report.csv"
        ReportService._write_csv(ReportService, path, payload)
        text = path.read_text(encoding="utf-8")
        assert "missing_values" in text and "duplicate_rows" in text
        assert text.splitlines()[0].startswith("Check,")
        assert len(text.strip().splitlines()) == len(payload["issues"]) + 1

    def test_csv_report_survives_an_empty_issue_list(
        self, tmp_path: Path, payload: dict
    ) -> None:
        payload["issues"] = []
        path = tmp_path / "empty.csv"
        ReportService._write_csv(ReportService, path, payload)
        assert path.read_text(encoding="utf-8").strip().splitlines() == [
            "Check,Column,Severity,Count,Recommended Fix"
        ]

    def test_xlsx_report_is_written_and_non_empty(self, tmp_path: Path, payload: dict) -> None:
        path = tmp_path / "report.xlsx"
        ReportService._write_xlsx(ReportService, path, payload)
        assert path.exists() and path.stat().st_size > 0

    def test_pdf_report_is_written_and_non_empty(self, tmp_path: Path, payload: dict) -> None:
        path = tmp_path / "report.pdf"
        ReportService._write_pdf(ReportService, path, payload)
        assert path.exists() and path.stat().st_size > 0
