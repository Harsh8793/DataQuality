"""DuckDB query engine: safe, read-only SQL execution over a dataset."""

from __future__ import annotations

import re
from dataclasses import dataclass

import duckdb
import pandas as pd

from app.core.logging import get_logger
from app.exceptions.base import BadRequestException

logger = get_logger(__name__)

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|copy|pragma|install|load)\b",
    re.IGNORECASE,
)


@dataclass
class QueryResult:
    """Result of executing a SQL query."""

    columns: list[str]
    rows: list[dict]
    row_count: int
    sql: str


class DuckDBEngine:
    """Executes validated, read-only SQL against an in-memory table.

    The dataset is always exposed under the fixed table name ``dataset`` so
    generated SQL is predictable and safe.
    """

    TABLE = "dataset"
    MAX_ROWS = 1000

    def validate(self, sql: str) -> str:
        """Validate that SQL is a single read-only SELECT and enforce a LIMIT."""
        cleaned = sql.strip().rstrip(";").strip()
        if not cleaned:
            raise BadRequestException("Empty SQL query.")
        if ";" in cleaned:
            raise BadRequestException("Multiple SQL statements are not allowed.")
        if not re.match(r"^\s*(with|select)\b", cleaned, re.IGNORECASE):
            raise BadRequestException("Only SELECT queries are permitted.")
        if _FORBIDDEN.search(cleaned):
            raise BadRequestException("Query contains a forbidden keyword.")
        if not re.search(r"\blimit\b", cleaned, re.IGNORECASE):
            cleaned = f"{cleaned} LIMIT {self.MAX_ROWS}"
        return cleaned

    def evaluate_condition(
        self, df: pd.DataFrame, condition: str, sample_limit: int = 200
    ) -> tuple[int, list[int], list[str], list[dict]]:
        """Evaluate a boolean WHERE condition and return matching rows.

        Returns ``(count, row_indices, columns, sample_rows)`` where the rows are
        those for which ``condition`` is true. Used by custom validations.
        """
        cond = (condition or "").strip().rstrip(";").strip()
        if not cond:
            raise BadRequestException("Empty validation condition.")
        if ";" in cond or _FORBIDDEN.search(cond):
            raise BadRequestException("Condition contains forbidden SQL.")

        con = duckdb.connect(database=":memory:")
        try:
            tmp = df.reset_index(drop=True).copy()
            tmp.insert(0, "__row_index", range(len(tmp)))
            con.register(self.TABLE, tmp)
            try:
                count = int(con.execute(f"SELECT COUNT(*) FROM {self.TABLE} WHERE {cond}").fetchone()[0])
                sample_df = con.execute(
                    f"SELECT * FROM {self.TABLE} WHERE {cond} LIMIT {sample_limit}"
                ).fetch_df()
            except duckdb.Error as exc:
                raise BadRequestException(f"Invalid condition: {exc}") from exc
        finally:
            con.close()

        indices = [int(i) for i in sample_df["__row_index"].tolist()]
        sample_df = sample_df.drop(columns=["__row_index"])
        sample_df = sample_df.astype(object).where(pd.notna(sample_df), None)
        return count, indices, [str(c) for c in sample_df.columns], sample_df.to_dict(orient="records")

    def execute(self, df: pd.DataFrame, sql: str) -> QueryResult:
        """Validate and run SQL against the DataFrame, returning rows."""
        safe_sql = self.validate(sql)
        con = duckdb.connect(database=":memory:")
        try:
            con.register(self.TABLE, df)
            result_df = con.execute(safe_sql).fetch_df()
        except duckdb.Error as exc:
            raise BadRequestException(f"SQL execution failed: {exc}") from exc
        finally:
            con.close()

        result_df = result_df.head(self.MAX_ROWS)
        rows = result_df.astype(object).where(pd.notna(result_df), None).to_dict(orient="records")
        return QueryResult(
            columns=[str(c) for c in result_df.columns],
            rows=rows,
            row_count=len(rows),
            sql=safe_sql,
        )
