"""Quality-check engine: 20+ deterministic checks registered by dimension.

Each check is a small pure function that receives the DataFrame and its
profile and returns a list of :class:`QualityFinding`. Adding a new check is
as simple as writing a function and decorating it with ``@register`` -
open/closed principle, no runner changes required.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.constants.enums import Dimension, SemanticType, Severity
from app.core.engines.profiler import DatasetProfile
from app.validators.patterns import is_valid_date, is_valid_email, is_valid_phone, is_valid_url


@dataclass
class QualityFinding:
    """A single detected quality problem."""

    check_key: str
    dimension: str
    severity: str
    count: int
    column_name: str | None = None
    sample: list = field(default_factory=list)


CheckFn = Callable[[pd.DataFrame, DatasetProfile], list[QualityFinding]]
CHECKS: list[CheckFn] = []


def register(fn: CheckFn) -> CheckFn:
    """Register a quality-check function in the global registry."""
    CHECKS.append(fn)
    return fn


def _samples(series: pd.Series, mask: pd.Series, limit: int = 5) -> list:
    """Return up to ``limit`` example values for a boolean mask."""
    return [str(v) for v in series[mask].dropna().unique()[:limit]]


# ====================================================================== #
# COMPLETENESS
# ====================================================================== #
@register
def check_missing_values(df: pd.DataFrame, profile: DatasetProfile) -> list[QualityFinding]:
    """Flag columns containing missing/null values."""
    findings = []
    for col in profile.columns:
        if col.null_count > 0:
            sev = (
                Severity.CRITICAL if col.null_pct > 50
                else Severity.HIGH if col.null_pct > 20
                else Severity.MEDIUM if col.null_pct > 5
                else Severity.LOW
            )
            findings.append(QualityFinding(
                "missing_values", Dimension.COMPLETENESS, sev, col.null_count,
                col.name, [f"{col.null_pct}% null"],
            ))
    return findings


@register
def check_blank_strings(df: pd.DataFrame, profile: DatasetProfile) -> list[QualityFinding]:
    """Flag object columns with empty/whitespace-only strings."""
    findings = []
    for name in df.select_dtypes(include="object").columns:
        s = df[name].dropna().astype(str)
        mask = s.str.strip() == ""
        count = int(mask.sum())
        if count:
            findings.append(QualityFinding(
                "blank_strings", Dimension.COMPLETENESS, Severity.MEDIUM, count, str(name),
            ))
    return findings


# ====================================================================== #
# UNIQUENESS
# ====================================================================== #
@register
def check_duplicate_rows(df: pd.DataFrame, profile: DatasetProfile) -> list[QualityFinding]:
    """Flag fully duplicated rows."""
    count = int(df.duplicated().sum())
    if count:
        sev = Severity.HIGH if count / max(len(df), 1) > 0.05 else Severity.MEDIUM
        return [QualityFinding("duplicate_rows", Dimension.UNIQUENESS, sev, count)]
    return []


@register
def check_duplicate_columns(df: pd.DataFrame, profile: DatasetProfile) -> list[QualityFinding]:
    """Flag columns whose values are identical to another column.

    Empty (all-null) and constant columns are skipped: two all-null or two
    all-zero columns are trivially "identical" but aren't meaningful duplicates,
    and they're already reported by the missing-values / constant-column checks.
    Only columns with at least two distinct non-null values are compared.
    """
    trivial = {c.name for c in profile.columns if c.distinct_count <= 1}
    findings, seen = [], {}
    for name in df.columns:
        if str(name) in trivial:
            continue
        key = tuple(df[name].fillna("__NA__").astype(str).tolist())
        if key in seen:
            # sample[0] is the column it duplicates (surfaced in the explanation).
            findings.append(QualityFinding(
                "duplicate_columns", Dimension.UNIQUENESS, Severity.MEDIUM, 1, str(name),
                [seen[key]],
            ))
        else:
            seen[key] = str(name)
    return findings


@register
def check_constant_columns(df: pd.DataFrame, profile: DatasetProfile) -> list[QualityFinding]:
    """Flag columns that carry a single constant value (no information)."""
    return [
        QualityFinding("constant_column", Dimension.UNIQUENESS, Severity.LOW, 1, col.name)
        for col in profile.columns
        if col.distinct_count <= 1 and profile.row_count > 1
    ]


@register
def check_high_cardinality(df: pd.DataFrame, profile: DatasetProfile) -> list[QualityFinding]:
    """Flag non-id text columns where nearly every value is unique."""
    findings = []
    for col in profile.columns:
        if (
            col.semantic_type in {SemanticType.TEXT, SemanticType.CATEGORICAL}
            and col.cardinality_ratio > 0.9
            and profile.row_count > 20
        ):
            findings.append(QualityFinding(
                "high_cardinality", Dimension.UNIQUENESS, Severity.INFO, col.distinct_count, col.name,
            ))
    return findings


@register
def check_low_cardinality(df: pd.DataFrame, profile: DatasetProfile) -> list[QualityFinding]:
    """Flag numeric columns that behave like low-cardinality categories."""
    findings = []
    for col in profile.columns:
        if col.semantic_type in {SemanticType.NUMERIC, SemanticType.INTEGER} and col.distinct_count <= 2 and profile.row_count > 20:
            findings.append(QualityFinding(
                "low_cardinality", Dimension.UNIQUENESS, Severity.INFO, col.distinct_count, col.name,
            ))
    return findings


# ====================================================================== #
# VALIDITY
# ====================================================================== #
def _validity_check(df, profile, sem_type, validator, key) -> list[QualityFinding]:
    findings = []
    for col in profile.columns:
        if col.semantic_type != sem_type:
            continue
        s = df[col.name].dropna().astype(str)
        mask = ~s.map(validator)
        count = int(mask.sum())
        if count:
            findings.append(QualityFinding(
                key, Dimension.VALIDITY, Severity.HIGH, count, col.name, _samples(s, mask),
            ))
    return findings


@register
def check_invalid_emails(df, profile):
    """Flag malformed values in email columns."""
    return _validity_check(df, profile, SemanticType.EMAIL, is_valid_email, "invalid_email")


@register
def check_invalid_phones(df, profile):
    """Flag malformed values in phone columns."""
    return _validity_check(df, profile, SemanticType.PHONE, is_valid_phone, "invalid_phone")


@register
def check_invalid_urls(df, profile):
    """Flag malformed values in URL columns."""
    return _validity_check(df, profile, SemanticType.URL, is_valid_url, "invalid_url")


@register
def check_invalid_dates(df, profile):
    """Flag unparseable values in date columns stored as text."""
    findings = []
    for col in profile.columns:
        if col.semantic_type != SemanticType.DATE:
            continue
        s = df[col.name].dropna().astype(str)
        mask = ~s.map(is_valid_date)
        count = int(mask.sum())
        if count:
            findings.append(QualityFinding(
                "invalid_date", Dimension.VALIDITY, Severity.MEDIUM, count, col.name, _samples(s, mask),
            ))
    return findings


@register
def check_negative_values(df, profile):
    """Flag negative values in columns that should be non-negative."""
    findings = []
    for col in profile.columns:
        if col.semantic_type not in {SemanticType.CURRENCY, SemanticType.ZIP}:
            continue
        if not pd.api.types.is_numeric_dtype(df[col.name]):
            continue
        mask = df[col.name] < 0
        count = int(mask.sum())
        if count:
            findings.append(QualityFinding(
                "negative_values", Dimension.VALIDITY, Severity.MEDIUM, count, col.name,
            ))
    return findings


# ====================================================================== #
# CONSISTENCY
# ====================================================================== #
@register
def check_leading_trailing_spaces(df, profile):
    """Flag text values with leading or trailing whitespace."""
    findings = []
    for name in df.select_dtypes(include="object").columns:
        s = df[name].dropna().astype(str)
        mask = s != s.str.strip()
        count = int(mask.sum())
        if count:
            findings.append(QualityFinding(
                "whitespace", Dimension.CONSISTENCY, Severity.LOW, count, str(name), _samples(s, mask),
            ))
    return findings


@register
def check_case_inconsistency(df, profile):
    """Flag categorical columns whose values differ only by letter case."""
    findings = []
    for col in profile.columns:
        if col.semantic_type not in {SemanticType.CATEGORICAL, SemanticType.TEXT}:
            continue
        s = df[col.name].dropna().astype(str)
        if s.empty:
            continue
        collapsed = s.str.lower().str.strip().nunique()
        if collapsed < s.nunique():
            findings.append(QualityFinding(
                "case_inconsistency", Dimension.CONSISTENCY, Severity.LOW,
                int(s.nunique() - collapsed), col.name,
            ))
    return findings


@register
def check_mixed_types(df, profile):
    """Flag object columns that mix numbers and text values."""
    findings = []
    for name in df.select_dtypes(include="object").columns:
        s = df[name].dropna().astype(str)
        if s.empty:
            continue
        numeric = s.str.match(r"^-?\d+(\.\d+)?$")
        frac = numeric.mean()
        if 0.1 < frac < 0.9:
            findings.append(QualityFinding(
                "mixed_types", Dimension.CONSISTENCY, Severity.MEDIUM, int((~numeric).sum()), str(name),
            ))
    return findings


@register
def check_unicode_issues(df, profile):
    """Flag text values containing replacement or control characters."""
    findings = []
    for name in df.select_dtypes(include="object").columns:
        s = df[name].dropna().astype(str)
        mask = s.str.contains("�", regex=False) | s.str.contains(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", regex=True)
        count = int(mask.sum())
        if count:
            findings.append(QualityFinding(
                "unicode_issues", Dimension.CONSISTENCY, Severity.LOW, count, str(name),
            ))
    return findings


# ====================================================================== #
# ACCURACY
# ====================================================================== #
@register
def check_outliers(df, profile):
    """Flag numeric outliers using the 1.5*IQR rule."""
    findings = []
    for col in profile.columns:
        if col.semantic_type not in {SemanticType.NUMERIC, SemanticType.INTEGER, SemanticType.CURRENCY}:
            continue
        s = pd.to_numeric(df[col.name], errors="coerce").dropna()
        if len(s) < 10:
            continue
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        mask = (s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)
        count = int(mask.sum())
        if count:
            findings.append(QualityFinding(
                "outliers", Dimension.ACCURACY, Severity.LOW, count, col.name,
                [str(round(float(v), 2)) for v in s[mask].head(5)],
            ))
    return findings


@register
def check_datatype_mismatch(df, profile):
    """Flag text columns that are actually numeric (stored as strings)."""
    findings = []
    for name in df.select_dtypes(include="object").columns:
        s = df[name].dropna().astype(str)
        if s.empty:
            continue
        numeric = s.str.match(r"^-?\d+(\.\d+)?$")
        if numeric.mean() >= 0.95:
            findings.append(QualityFinding(
                "datatype_mismatch", Dimension.ACCURACY, Severity.MEDIUM, len(s), str(name),
                ["stored as text but numeric"],
            ))
    return findings


# ====================================================================== #
# INTEGRITY
# ====================================================================== #
@register
def check_id_uniqueness(df, profile):
    """Flag id columns that contain duplicate identifiers."""
    findings = []
    for col in profile.columns:
        if col.semantic_type != SemanticType.ID:
            continue
        dup = int(df[col.name].dropna().duplicated().sum())
        if dup:
            findings.append(QualityFinding(
                "duplicate_ids", Dimension.INTEGRITY, Severity.HIGH, dup, col.name,
            ))
    return findings


@register
def check_empty_dataset(df, profile):
    """Flag an entirely empty dataset."""
    if profile.row_count == 0:
        return [QualityFinding("empty_dataset", Dimension.INTEGRITY, Severity.CRITICAL, 1)]
    return []


class QualityEngine:
    """Runs every registered quality check and aggregates the findings."""

    def run(self, df: pd.DataFrame, profile: DatasetProfile) -> list[QualityFinding]:
        """Execute all registered checks, isolating individual failures."""
        findings: list[QualityFinding] = []
        for check in CHECKS:
            try:
                findings.extend(check(df, profile))
            except Exception:  # noqa: BLE001 - one bad check must not abort analysis
                continue
        return findings
