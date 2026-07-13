"""Profiling engine: infer physical + semantic types and compute statistics."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.constants.enums import SemanticType
from app.core.logging import get_logger
from app.validators.patterns import (
    is_valid_date,
    is_valid_email,
    is_valid_phone,
    is_valid_url,
    is_valid_zip,
    looks_like_currency,
)

logger = get_logger(__name__)

# Column-name hints that boost semantic-type inference.
_NAME_HINTS: dict[str, SemanticType] = {
    "email": SemanticType.EMAIL,
    "e-mail": SemanticType.EMAIL,
    "phone": SemanticType.PHONE,
    "mobile": SemanticType.PHONE,
    "contact": SemanticType.PHONE,
    "zip": SemanticType.ZIP,
    "postal": SemanticType.ZIP,
    "url": SemanticType.URL,
    "website": SemanticType.URL,
    "link": SemanticType.URL,
    "lat": SemanticType.LATITUDE,
    "latitude": SemanticType.LATITUDE,
    "lon": SemanticType.LONGITUDE,
    "lng": SemanticType.LONGITUDE,
    "longitude": SemanticType.LONGITUDE,
    "price": SemanticType.CURRENCY,
    "amount": SemanticType.CURRENCY,
    "salary": SemanticType.CURRENCY,
    "revenue": SemanticType.CURRENCY,
    "cost": SemanticType.CURRENCY,
    "id": SemanticType.ID,
    "date": SemanticType.DATE,
    "created": SemanticType.DATETIME,
}


@dataclass
class ColumnProfile:
    """Profile for a single column."""

    name: str
    ordinal: int
    physical_type: str
    semantic_type: str
    null_count: int
    null_pct: float
    distinct_count: int
    cardinality_ratio: float
    min_val: str | None = None
    max_val: str | None = None
    mean_val: float | None = None
    std_val: float | None = None
    sample_values: list = field(default_factory=list)


@dataclass
class DatasetProfile:
    """Full dataset profile."""

    row_count: int
    col_count: int
    memory_bytes: int
    columns: list[ColumnProfile]


class Profiler:
    """Computes a :class:`DatasetProfile` from a DataFrame."""

    SAMPLE_LIMIT = 5
    INFER_SAMPLE = 200

    def profile(self, df: pd.DataFrame) -> DatasetProfile:
        """Profile every column of the DataFrame."""
        columns = [self._profile_column(df, name, idx) for idx, name in enumerate(df.columns)]
        return DatasetProfile(
            row_count=int(len(df)),
            col_count=int(df.shape[1]),
            memory_bytes=int(df.memory_usage(deep=True).sum()),
            columns=columns,
        )

    def _profile_column(self, df: pd.DataFrame, name: str, ordinal: int) -> ColumnProfile:
        series = df[name]
        n = len(series)
        null_count = int(series.isna().sum())
        non_null = series.dropna()
        distinct = int(non_null.nunique())

        min_val = max_val = None
        mean_val = std_val = None
        if pd.api.types.is_numeric_dtype(series) and not non_null.empty:
            min_val, max_val = str(non_null.min()), str(non_null.max())
            mean_val = float(non_null.mean())
            std_val = float(non_null.std()) if len(non_null) > 1 else 0.0
        elif not non_null.empty:
            try:
                min_val, max_val = str(non_null.min()), str(non_null.max())
            except TypeError:
                min_val = max_val = None

        semantic = self._infer_semantic_type(name, series, non_null)
        samples = [self._jsonify(v) for v in non_null.head(self.SAMPLE_LIMIT).tolist()]

        return ColumnProfile(
            name=str(name),
            ordinal=ordinal,
            physical_type=str(series.dtype),
            semantic_type=semantic,
            null_count=null_count,
            null_pct=round(null_count / n * 100, 2) if n else 0.0,
            distinct_count=distinct,
            cardinality_ratio=round(distinct / n, 4) if n else 0.0,
            min_val=min_val,
            max_val=max_val,
            mean_val=mean_val,
            std_val=std_val,
            sample_values=samples,
        )

    # ---- semantic inference ------------------------------------------ #
    def _infer_semantic_type(self, name: str, series: pd.Series, non_null: pd.Series) -> str:
        """Infer the business meaning of a column from name + value patterns."""
        lname = str(name).lower()

        if pd.api.types.is_bool_dtype(series):
            return SemanticType.BOOLEAN
        if pd.api.types.is_datetime64_any_dtype(series):
            return SemanticType.DATETIME

        if pd.api.types.is_numeric_dtype(series):
            return self._infer_numeric_semantic(lname, non_null)

        # Object/text columns: sample and test value patterns.
        sample = non_null.astype(str).head(self.INFER_SAMPLE)
        if sample.empty:
            return self._hint_or(lname, SemanticType.TEXT)

        pattern_type = self._infer_by_pattern(sample)
        if pattern_type is not None:
            return pattern_type

        # Low cardinality object columns are categorical.
        if len(non_null) and non_null.nunique() / len(non_null) < 0.5 and non_null.nunique() <= 50:
            return SemanticType.CATEGORICAL
        return self._hint_or(lname, SemanticType.TEXT)

    def _infer_numeric_semantic(self, lname: str, non_null: pd.Series) -> str:
        for hint, sem in _NAME_HINTS.items():
            if hint in lname and sem in {
                SemanticType.CURRENCY,
                SemanticType.LATITUDE,
                SemanticType.LONGITUDE,
                SemanticType.ZIP,
                SemanticType.ID,
            }:
                return sem
        if not non_null.empty:
            lo, hi = float(non_null.min()), float(non_null.max())
            if "lat" in lname and -90 <= lo and hi <= 90:
                return SemanticType.LATITUDE
            if ("lon" in lname or "lng" in lname) and -180 <= lo and hi <= 180:
                return SemanticType.LONGITUDE
        if pd.api.types.is_integer_dtype(non_null):
            return SemanticType.INTEGER
        return SemanticType.NUMERIC

    def _infer_by_pattern(self, sample: pd.Series) -> str | None:
        """Return a semantic type if >=70% of sampled values match a pattern."""
        checks = (
            (SemanticType.EMAIL, is_valid_email),
            (SemanticType.URL, is_valid_url),
            (SemanticType.ZIP, is_valid_zip),
            (SemanticType.PHONE, is_valid_phone),
            (SemanticType.CURRENCY, looks_like_currency),
            (SemanticType.DATE, is_valid_date),
        )
        total = len(sample)
        for sem, fn in checks:
            hits = sum(1 for v in sample if fn(v))
            if hits / total >= 0.7:
                return sem
        return None

    def _hint_or(self, lname: str, default: SemanticType) -> str:
        for hint, sem in _NAME_HINTS.items():
            if hint in lname:
                return sem
        return default

    @staticmethod
    def _jsonify(value: object) -> object:
        """Convert numpy/pandas scalars into JSON-serializable primitives."""
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return float(value)
        if isinstance(value, (np.bool_,)):
            return bool(value)
        return str(value) if not isinstance(value, (int, float, bool, str)) else value
