"""Cleaning engine: deterministic, idempotent data-cleaning transforms."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.constants.enums import SemanticType
from app.core.engines.profiler import DatasetProfile
from app.validators.patterns import is_valid_date, is_valid_email, is_valid_phone, is_valid_url

# Contact/identifier columns must never be imputed with a guessed value.
_NO_FILL_TYPES = {SemanticType.EMAIL, SemanticType.PHONE, SemanticType.URL, SemanticType.ID}
# Validators used to quarantine (null out) values that fail validation.
_QUARANTINE_VALIDATORS = {
    SemanticType.EMAIL: is_valid_email,
    SemanticType.PHONE: is_valid_phone,
    SemanticType.URL: is_valid_url,
    SemanticType.DATE: is_valid_date,
}

# Common country / gender normalization maps (extendable).
_COUNTRY_MAP = {
    "usa": "United States", "us": "United States", "u.s.a.": "United States",
    "united states of america": "United States", "uk": "United Kingdom",
    "u.k.": "United Kingdom", "uae": "United Arab Emirates",
}
_GENDER_MAP = {
    "m": "Male", "male": "Male", "f": "Female", "female": "Female",
    "man": "Male", "woman": "Female",
}


# Cap stored per-op row indices so operation payloads stay small.
_MAX_TRACKED_ROWS = 200


def _cap(indices) -> list[int]:
    """Return up to ``_MAX_TRACKED_ROWS`` sorted original-row indices."""
    return sorted(int(i) for i in indices)[:_MAX_TRACKED_ROWS]


@dataclass
class CleaningOp:
    """Record of a single cleaning operation applied."""

    op: str
    column: str | None
    rows_affected: int
    detail: str = ""
    # Original-frame row indices this op touched (capped for payload size).
    rows: list[int] = field(default_factory=list)


@dataclass
class CleaningResult:
    """Outcome of cleaning: the new frame plus an audit trail of ops."""

    df: pd.DataFrame
    operations: list[CleaningOp] = field(default_factory=list)


class Cleaner:
    """Applies a standard suite of cleaning transforms to a DataFrame."""

    def clean(self, df: pd.DataFrame, profile: DatasetProfile) -> CleaningResult:
        """Run all cleaning steps and return the cleaned frame + audit trail.

        The original positional index is preserved through every step (and only
        reset at the end) so each op can report which ORIGINAL rows it touched.
        """
        out = df.reset_index(drop=True).copy()
        ops: list[CleaningOp] = []

        out, ops_ = self._trim_spaces(out)
        ops += ops_
        out, ops_ = self._remove_duplicates(out)
        ops += ops_
        out, ops_ = self._quarantine_invalid(out, profile)
        ops += ops_
        out, ops_ = self._fill_missing(out, profile)
        ops += ops_
        out, ops_ = self._standardize_categoricals(out, profile)
        ops += ops_
        out, ops_ = self._normalize_domains(out)
        ops += ops_
        out, ops_ = self._convert_numeric_text(out)
        ops += ops_
        out, ops_ = self._cap_outliers(out, profile)
        ops += ops_
        return CleaningResult(df=out.reset_index(drop=True), operations=ops)

    def _trim_spaces(self, df):
        ops, affected, touched = [], 0, set()
        for name in df.select_dtypes(include="object").columns:
            before = df[name].copy()
            df[name] = df[name].map(lambda v: v.strip() if isinstance(v, str) else v)
            changed_mask = before.fillna("") != df[name].fillna("")
            affected += int(changed_mask.sum())
            touched.update(df.index[changed_mask])
        if affected:
            ops.append(CleaningOp("trim_spaces", None, affected,
                                  "Trimmed leading/trailing whitespace", _cap(touched)))
        return df, ops

    def _remove_duplicates(self, df):
        dup_mask = df.duplicated()
        removed = int(dup_mask.sum())
        if not removed:
            return df, []
        rows = _cap(df.index[dup_mask])
        df = df[~dup_mask]
        return df, [CleaningOp("remove_duplicates", None, removed,
                               f"Removed {removed} duplicate rows", rows)]

    def _quarantine_invalid(self, df, profile):
        """Null out values that fail validation (invalid email/phone/url/date).

        Genuinely invalid values cannot be repaired automatically, so they are
        quarantined (set to null) rather than left to corrupt downstream use.
        """
        ops = []
        for col in profile.columns:
            validator = _QUARANTINE_VALIDATORS.get(col.semantic_type)
            if validator is None or col.name not in df.columns:
                continue
            series = df[col.name]
            mask = series.notna() & ~series.astype(str).map(validator)
            count = int(mask.sum())
            if count:
                rows = _cap(df.index[mask])
                df.loc[mask, col.name] = None
                ops.append(CleaningOp("quarantine_invalid", col.name, count,
                                      f"Quarantined {count} invalid {col.semantic_type} values", rows))
        return df, ops

    def _fill_missing(self, df, profile):
        ops = []
        for col in profile.columns:
            if col.name not in df.columns or col.semantic_type in _NO_FILL_TYPES:
                continue
            # Recompute nulls: earlier steps (quarantine) may have added some.
            if int(df[col.name].isna().sum()) == 0:
                continue
            series = df[col.name]
            if pd.api.types.is_numeric_dtype(series):
                fill = series.median()
                strategy = "median"
            else:
                mode = series.mode()
                fill = mode.iloc[0] if not mode.empty else "Unknown"
                strategy = "mode"
            filled = int(series.isna().sum())
            rows = _cap(df.index[series.isna()])
            df[col.name] = series.fillna(fill)
            ops.append(CleaningOp("fill_missing", col.name, filled,
                                  f"Filled {filled} nulls with {strategy}", rows))
        return df, ops

    def _standardize_categoricals(self, df, profile):
        ops, affected, touched = [], 0, set()
        for col in profile.columns:
            if col.semantic_type != SemanticType.CATEGORICAL or col.name not in df.columns:
                continue
            series = df[col.name]
            if not pd.api.types.is_object_dtype(series):
                continue
            before = series.copy()
            df[col.name] = series.map(lambda v: v.strip().title() if isinstance(v, str) else v)
            changed_mask = before.fillna("") != df[col.name].fillna("")
            affected += int(changed_mask.sum())
            touched.update(df.index[changed_mask])
        if affected:
            ops.append(CleaningOp("standardize_text", None, affected,
                                  "Standardized categorical casing", _cap(touched)))
        return df, ops

    def _normalize_domains(self, df):
        ops = []
        for name in df.columns:
            lname = str(name).lower()
            if "country" in lname and pd.api.types.is_object_dtype(df[name]):
                df[name], n, rows = self._apply_map(df[name], _COUNTRY_MAP)
                if n:
                    ops.append(CleaningOp("normalize_country", str(name), n, "Normalized country names", rows))
            if "gender" in lname or "sex" == lname:
                df[name], n, rows = self._apply_map(df[name], _GENDER_MAP)
                if n:
                    ops.append(CleaningOp("normalize_gender", str(name), n, "Normalized gender values", rows))
        return df, ops

    @staticmethod
    def _apply_map(series, mapping):
        def _map(v):
            if isinstance(v, str) and v.strip().lower() in mapping:
                return mapping[v.strip().lower()]
            return v

        before = series.copy()
        mapped = series.map(_map)
        changed_mask = before.fillna("") != mapped.fillna("")
        return mapped, int(changed_mask.sum()), _cap(series.index[changed_mask])

    def _convert_numeric_text(self, df):
        ops = []
        for name in df.select_dtypes(include="object").columns:
            s = df[name].dropna().astype(str)
            if s.empty:
                continue
            if s.str.match(r"^-?\d+(\.\d+)?$").mean() >= 0.95:
                rows = _cap(df.index[df[name].notna()])
                df[name] = pd.to_numeric(df[name], errors="coerce")
                ops.append(CleaningOp("convert_datatype", str(name), len(s),
                                      "Converted text to numeric", rows))
        return df, ops

    def _cap_outliers(self, df, profile):
        ops = []
        for col in profile.columns:
            if col.semantic_type not in {SemanticType.NUMERIC, SemanticType.INTEGER, SemanticType.CURRENCY}:
                continue
            if col.name not in df.columns:
                continue
            s = pd.to_numeric(df[col.name], errors="coerce")
            valid = s.dropna()
            if len(valid) < 10:
                continue
            q1, q3 = valid.quantile(0.25), valid.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            mask = (s < lo) | (s > hi)
            count = int(mask.sum())
            if count:
                rows = _cap(df.index[mask])
                df[col.name] = s.clip(lower=lo, upper=hi)
                ops.append(CleaningOp("cap_outliers", col.name, count,
                                      f"Capped {count} outliers to IQR bounds", rows))
        return df, ops
