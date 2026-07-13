"""Resolve which rows are affected by a specific quality issue.

Given a dataframe, a check key and a column, return a boolean mask selecting
the offending rows so the UI can display exactly what triggered the issue.
"""

from __future__ import annotations

import pandas as pd

from app.validators.patterns import (
    is_valid_date,
    is_valid_email,
    is_valid_phone,
    is_valid_url,
)


def _none(df: pd.DataFrame) -> pd.Series:
    return pd.Series([False] * len(df), index=df.index)


def affected_mask(df: pd.DataFrame, check_key: str, column: str | None) -> pd.Series:
    """Return a boolean mask of rows affected by ``check_key`` on ``column``."""
    if check_key == "duplicate_rows":
        return df.duplicated(keep=False)

    if not column or column not in df.columns:
        return _none(df)

    s = df[column]
    text = s.astype(str)

    if check_key == "missing_values":
        return s.isna()
    if check_key == "blank_strings":
        return s.notna() & (text.str.strip() == "")
    if check_key == "whitespace":
        return s.notna() & (text != text.str.strip())
    if check_key == "invalid_email":
        return s.notna() & ~text.map(is_valid_email)
    if check_key == "invalid_phone":
        return s.notna() & ~text.map(is_valid_phone)
    if check_key == "invalid_url":
        return s.notna() & ~text.map(is_valid_url)
    if check_key == "invalid_date":
        return s.notna() & ~text.map(is_valid_date)
    if check_key == "negative_values":
        return pd.to_numeric(s, errors="coerce") < 0
    if check_key == "duplicate_ids":
        return s.notna() & s.duplicated(keep=False)
    if check_key == "outliers":
        num = pd.to_numeric(s, errors="coerce")
        q1, q3 = num.quantile(0.25), num.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            return _none(df)
        return (num < q1 - 1.5 * iqr) | (num > q3 + 1.5 * iqr)
    if check_key == "unicode_issues":
        return s.notna() & (
            text.str.contains("�", regex=False)
            | text.str.contains(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", regex=True)
        )
    if check_key == "mixed_types":
        numeric = text.str.match(r"^-?\d+(\.\d+)?$")
        frac = numeric[s.notna()].mean() if s.notna().any() else 0
        # The minority type is the offending one.
        return s.notna() & (~numeric if frac >= 0.5 else numeric)
    if check_key == "case_inconsistency":
        vals = text[s.notna()]
        if vals.empty:
            return _none(df)
        canonical = vals.groupby(vals.str.lower().str.strip()).agg(lambda x: x.value_counts().index[0])

        def _off(value: object) -> bool:
            key = str(value).lower().strip()
            return key in canonical.index and canonical[key] != str(value)

        return s.notna() & text.map(_off)

    # Column-level checks (constant, cardinality, duplicate columns, datatype
    # mismatch): every non-null value illustrates the problem.
    if check_key in {
        "constant_column",
        "high_cardinality",
        "low_cardinality",
        "duplicate_columns",
        "datatype_mismatch",
    }:
        return s.notna()

    return _none(df)
