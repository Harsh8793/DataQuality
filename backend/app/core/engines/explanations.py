"""Deterministic, per-issue quality explanations.

The AI explainer is keyed by check type only, so it can't correctly name the
column or count for every one of (potentially) 100+ issues — it would repeat one
column/number everywhere. These templates inject the *actual* column and count
for each issue, so every explanation is factual and specific. Zero tokens.
"""

from __future__ import annotations

# check_key -> (cause, business_impact, fix_template).  {col} is substituted.
_KB: dict[str, tuple[str, str, str]] = {
    "missing_values": (
        "the value was never recorded or was lost in transfer",
        "Incomplete records skew counts and averages and bias any grouping that uses this column.",
        "Impute {col} (median for numbers, most-frequent for text) or drop the affected rows.",
    ),
    "blank_strings": (
        "fields were submitted empty or as whitespace only",
        "Blanks masquerade as filled values and quietly inflate completeness metrics.",
        "Convert blanks in {col} to null, then impute or collect real values.",
    ),
    "whitespace": (
        "values carry leading or trailing spaces from manual entry or exports",
        "Identical values fail to match in joins, filters and group-bys.",
        "Trim whitespace from {col}.",
    ),
    "duplicate_rows": (
        "the same record was ingested more than once",
        "Duplicates inflate counts and distort every aggregate metric.",
        "Remove the duplicate rows (keep one copy).",
    ),
    "duplicate_ids": (
        "the same identifier appears on multiple rows",
        "Lookups and joins on {col} return multiple matches and corrupt downstream reports.",
        "Keep one row per {col}, or assign new unique identifiers.",
    ),
    "invalid_email": (
        "values do not match a valid email format",
        "Undeliverable messages, bounce costs and wasted outreach.",
        "Validate and correct {col}; quarantine values that can't be repaired.",
    ),
    "invalid_phone": (
        "values do not match a valid phone format",
        "Failed calls/SMS and wasted contact attempts.",
        "Standardize {col} to a consistent phone format; quarantine invalid ones.",
    ),
    "invalid_url": (
        "values are not well-formed URLs",
        "Broken links in reports and applications.",
        "Repair or quarantine the invalid URLs in {col}.",
    ),
    "invalid_date": (
        "values are in mixed or impossible date formats",
        "Time-based analysis (trends, ageing) becomes unreliable.",
        "Parse {col} to one date format; quarantine unparseable values.",
    ),
    "negative_values": (
        "a positive-only measure contains negative numbers",
        "Totals and averages are silently understated.",
        "Confirm whether negatives are valid in {col}; quarantine or correct them.",
    ),
    "outliers": (
        "values fall far outside the typical range",
        "A handful of extremes can distort averages and charts.",
        "Verify the extremes in {col}; cap or exclude confirmed errors.",
    ),
    "case_inconsistency": (
        "the same value appears in different capitalizations",
        "Variants like 'east' and 'East' are counted as separate groups.",
        "Standardize {col} to one canonical casing.",
    ),
    "mixed_types": (
        "numbers and text are mixed in one column",
        "The column can't be aggregated or sorted reliably.",
        "Convert {col} to its majority type; quarantine the rest.",
    ),
    "constant_column": (
        "every row holds the same value",
        "The column adds no analytical value.",
        "Drop {col}, or verify the feed that populates it.",
    ),
    "duplicate_columns": (
        "this column duplicates another column's data",
        "Redundant storage and ambiguous joins.",
        "Drop one of the duplicate columns.",
    ),
    "high_cardinality": (
        "almost every value is unique",
        "Unsuitable for grouping and may hide identifiers or PII.",
        "Confirm the role of {col}; exclude it from breakdowns.",
    ),
    "low_cardinality": (
        "the column has very few distinct values",
        "Limited analytical signal.",
        "Confirm this is expected for {col}.",
    ),
    "unicode_issues": (
        "the text contains corrupted or control characters",
        "Garbled text in reports and failed matching.",
        "Re-import {col} with the correct encoding.",
    ),
    "datatype_mismatch": (
        "values don't match the column's expected type",
        "Type casts fail or silently corrupt values downstream.",
        "Convert {col} to its correct type.",
    ),
    "empty_dataset": (
        "the file contained headers but no data rows",
        "There is nothing to analyze.",
        "Upload a file that contains data rows.",
    ),
}

_DEFAULT = (
    "the values did not pass this quality check",
    "May reduce the trustworthiness of downstream analysis.",
    "Review and remediate {col}.",
)

# Column-level checks: whole-column statements (no per-row percentage).
_COLUMN_LEVEL_CAUSE: dict[str, str] = {
    "constant_column": "holds the same value in every one of the {total} rows, so it carries no information",
    "duplicate_columns": "contains exactly the same data as another column",
    "high_cardinality": "has a distinct value in almost every row",
    "low_cardinality": "has only a couple of distinct values across the whole column",
    "datatype_mismatch": "contains values that don't match its expected data type",
}


def explain_issue(
    check_key: str, column: str | None, count: int, total: int, ref_column: str | None = None
) -> dict:
    """Return a factual, column- and count-specific explanation for one issue.

    ``ref_column`` names the other column for duplicate-column findings so the
    claim is verifiable.
    """
    cause, impact, fix = _KB.get(check_key, _DEFAULT)
    col = column or "the dataset"
    pct = round(count / total * 100, 1) if total else 0.0
    fully_empty = check_key in {"missing_values", "blank_strings"} and total and count >= total

    if fully_empty:
        why = f"Every one of the {total} rows is empty in “{column}” — the column holds no data at all."
        fix_text = (
            f"Drop “{column}” — it is 100% empty, so there is nothing to impute from. "
            "Use the Edit or Cleaning tools to remove it."
        )
    elif check_key == "duplicate_columns" and ref_column:
        why = f"“{column}” contains exactly the same values as “{ref_column}” in every row."
        fix_text = f"If “{column}” is redundant with “{ref_column}”, drop one of them."
    elif check_key in _COLUMN_LEVEL_CAUSE:
        # Column-level checks describe the whole column — a per-row percentage
        # ("1 of 100 rows") is meaningless here.
        why = f"“{column}” {_COLUMN_LEVEL_CAUSE[check_key].format(total=total)}."
        fix_text = fix.format(col=col)
    elif column:
        why = f"{count} of {total} rows ({pct}%) are affected in “{column}” — {cause}."
        fix_text = fix.format(col=col)
    else:
        why = f"{count} rows are affected — {cause}."
        fix_text = fix.format(col=col)

    return {
        "problem": None,  # title is set separately (column-specific)
        "why": why,
        "business_impact": impact.format(col=col),
        "recommended_fix": fix_text,
        # Deterministic facts, not an AI guess — no confidence score.
        "confidence": None,
    }
