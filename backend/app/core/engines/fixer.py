"""Targeted issue fixer: apply ONE cleaning operation for a specific finding.

Unlike the full :class:`Cleaner` (one-click, all steps), this engine fixes a
single quality issue the user clicked on, e.g. "fill the nulls in this column"
or "drop the duplicate rows" — nothing else is touched.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.validators.patterns import is_valid_date, is_valid_email, is_valid_phone, is_valid_url

_VALIDATORS = {
    "invalid_email": is_valid_email,
    "invalid_phone": is_valid_phone,
    "invalid_url": is_valid_url,
    "invalid_date": is_valid_date,
}

def _is_no_fill_column(name: str) -> bool:
    """Contact/identifier columns must never be imputed with a guessed value."""
    lname = name.lower()
    return (
        any(k in lname for k in ("email", "phone", "url"))
        or lname == "id"
        or lname.endswith(("_id", " id"))
    )

# Check keys this engine knows how to repair (mirrored by the frontend).
FIXABLE_CHECKS = {
    "missing_values", "blank_strings", "whitespace", "duplicate_rows",
    "invalid_email", "invalid_phone", "invalid_url", "invalid_date",
    "negative_values", "outliers", "case_inconsistency", "mixed_types",
    "duplicate_ids", "constant_column", "duplicate_columns",
}


@dataclass
class FixResult:
    """Outcome of a targeted fix."""

    df: pd.DataFrame
    op: str
    rows_affected: int
    detail: str


class UnfixableIssueError(ValueError):
    """Raised when a check key has no automated targeted fix."""


def apply_fix(df: pd.DataFrame, check_key: str, column: str | None) -> FixResult:
    """Apply the targeted fix for ``check_key`` and return the new frame.

    Row-dropping fixes preserve the original index (no reset) so callers can
    diff before/after frames; reset the index before persisting.
    """
    if check_key == "duplicate_rows":
        dup = df.duplicated()
        n = int(dup.sum())
        out = df[~dup]
        return FixResult(out, "remove_duplicates", n, f"Removed {n} duplicate rows")

    if not column or column not in df.columns:
        raise UnfixableIssueError("This issue has no automated fix.")

    out = df.copy()
    s = out[column]

    if check_key == "missing_values" or check_key == "blank_strings":
        if check_key == "blank_strings":
            blank = s.notna() & (s.astype(str).str.strip() == "")
            out.loc[blank, column] = None
            s = out[column]
        nulls = int(s.isna().sum())
        if nulls == 0:
            return FixResult(out, "fill_missing", 0, "No missing values left to fill")
        if _is_no_fill_column(column):
            # Contact/id columns can't be guessed — drop the incomplete rows.
            out = out[s.notna()]
            return FixResult(out, "drop_incomplete", nulls,
                             f"Dropped {nulls} rows with missing {column} (cannot be imputed)")
        if pd.api.types.is_numeric_dtype(s):
            fill, strategy = s.median(), "median"
        else:
            mode = s.mode()
            fill, strategy = (mode.iloc[0] if not mode.empty else "Unknown"), "mode"
        out[column] = s.fillna(fill)
        return FixResult(out, "fill_missing", nulls, f"Filled {nulls} missing values with {strategy}")

    if check_key == "whitespace":
        text = s.astype(str)
        mask = s.notna() & (text != text.str.strip())
        n = int(mask.sum())
        out[column] = s.map(lambda v: v.strip() if isinstance(v, str) else v)
        return FixResult(out, "trim_spaces", n, f"Trimmed whitespace in {n} values")

    if check_key in _VALIDATORS:
        validator = _VALIDATORS[check_key]
        mask = s.notna() & ~s.astype(str).map(validator)
        n = int(mask.sum())
        out.loc[mask, column] = None
        return FixResult(out, "quarantine_invalid", n,
                         f"Quarantined {n} invalid values (set to null)")

    if check_key == "negative_values":
        num = pd.to_numeric(s, errors="coerce")
        mask = num < 0
        n = int(mask.sum())
        out.loc[mask, column] = None
        return FixResult(out, "quarantine_negative", n,
                         f"Quarantined {n} negative values (set to null)")

    if check_key == "outliers":
        num = pd.to_numeric(s, errors="coerce")
        q1, q3 = num.quantile(0.25), num.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            return FixResult(out, "cap_outliers", 0, "No spread to cap against")
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        mask = (num < lo) | (num > hi)
        n = int(mask.sum())
        out[column] = num.clip(lower=lo, upper=hi)
        return FixResult(out, "cap_outliers", n, f"Capped {n} outliers to IQR bounds")

    if check_key == "case_inconsistency":
        text = s.astype(str)
        vals = text[s.notna()]
        canonical = vals.groupby(vals.str.lower().str.strip()).agg(lambda x: x.value_counts().index[0])

        def _canon(v: object):
            if not isinstance(v, str):
                return v
            key = v.lower().strip()
            return canonical[key] if key in canonical.index else v

        before = s.copy()
        out[column] = s.map(_canon)
        n = int((before.fillna("") != out[column].fillna("")).sum())
        return FixResult(out, "standardize_case", n, f"Standardized casing of {n} values")

    if check_key == "mixed_types":
        text = s.astype(str)
        numeric = text.str.match(r"^-?\d+(\.\d+)?$")
        frac = numeric[s.notna()].mean() if s.notna().any() else 0
        if frac >= 0.5:
            # Mostly numeric: coerce, quarantining the text minority.
            n = int((s.notna() & ~numeric).sum())
            out[column] = pd.to_numeric(s, errors="coerce")
            return FixResult(out, "convert_datatype", n,
                             f"Converted column to numeric; quarantined {n} non-numeric values")
        n = int((s.notna() & numeric).sum())
        out.loc[s.notna() & numeric, column] = None
        return FixResult(out, "quarantine_minority", n,
                         f"Quarantined {n} numeric values in a text column")

    if check_key == "duplicate_ids":
        mask = s.notna() & s.duplicated(keep="first")
        n = int(mask.sum())
        out = out[~mask]
        return FixResult(out, "drop_duplicate_ids", n, f"Dropped {n} rows with duplicate {column}")

    if check_key in {"constant_column", "duplicate_columns"}:
        out = out.drop(columns=[column])
        return FixResult(out, "drop_column", len(out), f"Dropped column {column}")

    raise UnfixableIssueError("This issue has no automated fix.")
