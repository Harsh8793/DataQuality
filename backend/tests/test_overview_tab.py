"""Overview tab: file loading, profiling and the AI data story.

Covers ``core/engines/loader.py``, ``core/engines/profiler.py`` and the story
half of ``services/ai_service.py``.
"""

from __future__ import annotations

import io

import pandas as pd
import pytest

from app.core.engines.loader import DataLoader
from app.core.engines.profiler import Profiler
from app.exceptions.base import BadRequestException, UnsupportedFormatException
from app.services.ai_service import AiService


# --------------------------------------------------------------------------- #
# Loader
# --------------------------------------------------------------------------- #
class TestDataLoader:
    def test_loads_csv_and_reports_format(self) -> None:
        result = DataLoader().load(b"a,b\n1,2\n3,4\n", "csv")
        assert result.file_format == "csv"
        assert result.df.shape == (2, 2)
        assert result.delimiter == ","

    @pytest.mark.parametrize("delimiter", [";", "|", "~", "\t", "^"])
    def test_detects_uncommon_delimiters(self, delimiter: str) -> None:
        content = f"a{delimiter}b\n1{delimiter}2\n".encode()
        result = DataLoader().load(content, "csv")
        assert result.delimiter == delimiter
        assert list(result.df.columns) == ["a", "b"]

    def test_falls_back_to_comma_when_no_delimiter_found(self) -> None:
        result = DataLoader().load(b"single\n1\n2\n", "csv")
        assert result.delimiter == ","
        assert list(result.df.columns) == ["single"]

    def test_extension_is_case_insensitive_and_dot_tolerant(self) -> None:
        assert DataLoader().load(b"a,b\n1,2\n", ".CSV").file_format == "csv"

    def test_rejects_unsupported_extension(self) -> None:
        with pytest.raises(UnsupportedFormatException):
            DataLoader().load(b"x", "pdf")

    def test_loads_json_array(self) -> None:
        result = DataLoader().load(b'[{"a":1,"b":2},{"a":3,"b":4}]', "json")
        assert result.file_format == "json"
        assert result.df.shape == (2, 2)

    def test_loads_json_wrapped_in_data_key(self) -> None:
        result = DataLoader().load(b'{"data":[{"a":1},{"a":2}]}', "json")
        assert result.df.shape == (2, 1)

    def test_loads_parquet_without_encoding_or_delimiter(self, clean_frame: pd.DataFrame) -> None:
        buffer = io.BytesIO()
        clean_frame.to_parquet(buffer, index=False)
        result = DataLoader().load(buffer.getvalue(), "parquet")
        assert result.file_format == "parquet"
        assert result.encoding is None and result.delimiter is None
        assert result.df.shape == clean_frame.shape

    def test_corrupt_parquet_raises_readable_error(self) -> None:
        with pytest.raises(BadRequestException, match="Parquet"):
            DataLoader().load(b"definitely not parquet", "parquet")

    def test_corrupt_excel_raises_readable_error(self) -> None:
        with pytest.raises(BadRequestException, match="Excel"):
            DataLoader().load(b"definitely not excel", "xlsx")

    def test_non_utf8_bytes_still_load(self) -> None:
        # Latin-1 encoded accented text must not blow up the loader.
        result = DataLoader().load("name\nJosé\n".encode("latin-1"), "csv")
        assert result.df.shape == (1, 1)


# --------------------------------------------------------------------------- #
# Profiler
# --------------------------------------------------------------------------- #
class TestProfiler:
    def test_counts_rows_columns_and_nulls(self, messy_frame: pd.DataFrame) -> None:
        profile = Profiler().profile(messy_frame)
        assert profile.row_count == len(messy_frame)
        assert profile.col_count == messy_frame.shape[1]
        revenue = next(c for c in profile.columns if c.name == "revenue")
        assert revenue.null_count == 1
        assert revenue.null_pct == pytest.approx(100 / 7, abs=0.1)

    def test_infers_semantic_types(self, messy_frame: pd.DataFrame) -> None:
        by_name = {c.name: c.semantic_type for c in Profiler().profile(messy_frame).columns}
        assert by_name["email"] == "email"
        assert by_name["revenue"] in {"numeric", "currency"}
        assert by_name["quantity"] in {"integer", "numeric"}

    def test_distinct_and_cardinality_are_consistent(self, clean_frame: pd.DataFrame) -> None:
        region = next(c for c in Profiler().profile(clean_frame).columns if c.name == "region")
        assert region.distinct_count == 3
        assert 0 < region.cardinality_ratio <= 1

    def test_numeric_columns_carry_min_max_mean(self, clean_frame: pd.DataFrame) -> None:
        sales = next(c for c in Profiler().profile(clean_frame).columns if c.name == "sales")
        assert float(sales.min_val) == 10.0
        assert float(sales.max_val) == 40.0
        assert sales.mean_val == pytest.approx(25.0)

    def test_empty_frame_profiles_without_error(self) -> None:
        profile = Profiler().profile(pd.DataFrame({"a": []}))
        assert profile.row_count == 0
        assert profile.col_count == 1

    def test_all_null_column_is_fully_null(self) -> None:
        profile = Profiler().profile(pd.DataFrame({"a": [None, None, None]}))
        assert profile.columns[0].null_pct == 100.0

    def test_iso_dates_are_dates_not_phone_numbers(self) -> None:
        """Regression: "2024-01-05" satisfies the phone pattern too.

        When PHONE was tested first, every ISO date column was typed as a phone
        number — flagging it as PII and hiding it from time-series charts.
        """
        frame = pd.DataFrame({"sold_on": ["2024-01-05", "2024-02-05", "2024-03-05"]})
        assert Profiler().profile(frame).columns[0].semantic_type == "date"

    @pytest.mark.parametrize(
        ("values", "expected"),
        [
            (["+1 (555) 012-3456", "555-123-4567", "(555) 987 6543"], "phone"),
            (["90210", "10001", "60601"], "zip"),
            (["a@x.com", "b@x.com", "c@x.com"], "email"),
            (["$10.50", "$20.00", "$5.25"], "currency"),
            (["https://a.com", "https://b.com", "https://c.com"], "url"),
        ],
    )
    def test_pattern_types_survive_the_date_first_ordering(
        self, values: list[str], expected: str
    ) -> None:
        frame = pd.DataFrame({"col": values})
        assert Profiler().profile(frame).columns[0].semantic_type == expected

    def test_ordinals_follow_column_order(self, clean_frame: pd.DataFrame) -> None:
        profile = Profiler().profile(clean_frame)
        assert [c.ordinal for c in profile.columns] == list(range(len(profile.columns)))


# --------------------------------------------------------------------------- #
# Data story (deterministic fallback path)
# --------------------------------------------------------------------------- #
class TestFallbackStory:
    """The story must keep its bulleted shape when the LLM is unavailable."""

    def _story(self, frame: pd.DataFrame, report=None) -> str:
        profile = Profiler().profile(frame)
        dataset = type("Dataset", (), {"name": "demo", "id": 1})()
        return AiService._fallback_story(dataset, profile, report)

    def test_has_five_labelled_bullets(self, messy_frame: pd.DataFrame) -> None:
        lines = [line for line in self._story(messy_frame).splitlines() if line.strip()]
        assert len(lines) == 5
        assert all(line.startswith("• ") for line in lines)
        for label in ("What this data is", "Key measures", "Quality concerns",
                      "Sensitive data", "Do this next"):
            assert label in "\n".join(lines)

    def test_reports_real_row_and_column_counts(self, messy_frame: pd.DataFrame) -> None:
        story = self._story(messy_frame)
        assert f"{len(messy_frame):,} rows" in story
        assert f"{messy_frame.shape[1]} columns" in story

    def test_flags_pii_columns_when_present(self, messy_frame: pd.DataFrame) -> None:
        assert "email" in self._story(messy_frame)

    def test_says_so_when_no_pii_detected(self, clean_frame: pd.DataFrame) -> None:
        assert "no personal data columns" in self._story(clean_frame)

    def test_unscored_dataset_is_told_to_run_analysis(self, clean_frame: pd.DataFrame) -> None:
        story = self._story(clean_frame, report=None)
        assert "not been quality-scored" in story
        assert "run a quality analysis" in story

    def test_low_score_dataset_is_told_to_clean(self, clean_frame: pd.DataFrame) -> None:
        report = type("Report", (), {"overall_score": 60.0, "total_issues": 5})()
        story = self._story(clean_frame, report=report)
        assert "60" in story
        assert "one-click cleaning" in story

    def test_high_score_dataset_is_told_to_explore(self, clean_frame: pd.DataFrame) -> None:
        report = type("Report", (), {"overall_score": 97.0, "total_issues": 0})()
        assert "explore the data" in self._story(clean_frame, report=report)
