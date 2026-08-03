"""Chart recommendation engine: derive dashboard specs from a profile.

The backend decides *what* to chart (spec); the frontend decides *how* to
render it. Specs are plain dicts so they serialize directly to JSON.
"""

from __future__ import annotations

import re

import pandas as pd

from app.constants.enums import SemanticType
from app.core.engines.profiler import DatasetProfile

_NUMERIC = {SemanticType.NUMERIC, SemanticType.INTEGER, SemanticType.CURRENCY}
_CATEGORICAL = {SemanticType.CATEGORICAL, SemanticType.TEXT, SemanticType.BOOLEAN}
_TEMPORAL = {SemanticType.DATE, SemanticType.DATETIME}


def parse_dates(series: pd.Series) -> pd.Series:
    """Parse a date column that may hold several formats at once.

    Real uploads mix ``15/02/2024``, ``2024-04-10`` and junk in one column.
    A single ``to_datetime`` call parses only the rows matching whichever
    format it infers first and silently coerces the rest to NaT — which
    collapses a year of data onto one point. Try day-first and month-first
    parses and keep whichever recovers more rows.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return series

    best = pd.to_datetime(series, errors="coerce", format="mixed", dayfirst=False)
    for kwargs in ({"format": "mixed", "dayfirst": True}, {"dayfirst": True}, {}):
        try:
            candidate = pd.to_datetime(series, errors="coerce", **kwargs)
        except (ValueError, TypeError):
            continue
        if candidate.notna().sum() > best.notna().sum():
            best = candidate
    return best


class ChartRecommender:
    """Builds KPI cards and chart specifications for a dataset."""

    MAX_CHARTS = 6
    # Bars a chart can show before the tail is rolled into an "Other" slice.
    # Nothing is dropped — the remainder is aggregated, so totals still add up.
    MAX_CATEGORIES = 50
    OTHER_LABEL = "Other"
    # Points a scatter plots before it switches to an evenly-spaced sample
    # across the whole dataset (never the first N rows, which biases sorted data).
    MAX_SCATTER_POINTS = 5000

    # Pool caps to keep payloads reasonable on wide datasets.
    POOL_NUMERIC = 12
    POOL_CATEGORICAL = 8
    POOL_MAX_CHARTS = 24
    DEFAULT_KPIS = 4
    DEFAULT_CHARTS = 6

    def build(self, df: pd.DataFrame, profile: DatasetProfile) -> dict:
        """Return a dashboard spec: ``{kpis: [...], charts: [...]}``."""
        return {"kpis": self._kpis(df, profile), "charts": self._charts(df, profile)}

    # ---- widget pool (for the dashboard builder) --------------------- #
    def build_pool(self, df: pd.DataFrame, profile: DatasetProfile) -> dict:
        """Return the full pool of addable KPI + chart widgets, each with an id."""
        return {"kpis": self._kpi_pool(df, profile), "charts": self._chart_pool(df, profile)}

    # At most this many charts of the same type in the default dashboard, so
    # the starter view is a mix (bar/pie/line/scatter) rather than all pies.
    DEFAULT_PER_TYPE = 2

    def default_selection(self, pool: dict) -> dict:
        """Return the default selected widget ids (a sensible, varied starter view)."""
        charts = pool["charts"]
        picked: list[dict] = []
        type_count: dict[str, int] = {}
        # Pass 1: spread across chart types (cap per type) for visual variety.
        for c in charts:
            if len(picked) >= self.DEFAULT_CHARTS:
                break
            if type_count.get(c["type"], 0) < self.DEFAULT_PER_TYPE:
                picked.append(c)
                type_count[c["type"]] = type_count.get(c["type"], 0) + 1
        # Pass 2: fill any remaining slots with whatever's left.
        if len(picked) < self.DEFAULT_CHARTS:
            picked_ids = {c["id"] for c in picked}
            for c in charts:
                if c["id"] in picked_ids:
                    continue
                picked.append(c)
                if len(picked) >= self.DEFAULT_CHARTS:
                    break
        return {
            "kpis": [k["id"] for k in pool["kpis"][: self.DEFAULT_KPIS]],
            "charts": [c["id"] for c in picked],
        }

    def _kpi_pool(self, df: pd.DataFrame, profile: DatasetProfile) -> list[dict]:
        kpis = [
            {"id": "kpi:rows", "label": "Total Rows", "value": profile.row_count, "format": "number"},
            {"id": "kpi:cols", "label": "Columns", "value": profile.col_count, "format": "number"},
        ]
        numeric = [c for c in profile.columns if c.semantic_type in _NUMERIC]
        for col in numeric[: self.POOL_NUMERIC]:
            series = pd.to_numeric(df[col.name], errors="coerce")
            fmt = "currency" if col.semantic_type == SemanticType.CURRENCY else "number"
            has = series.notna().any()
            kpis.append({"id": f"kpi:avg:{col.name}", "label": f"Avg {col.name}",
                         "value": round(float(series.mean()), 2) if has else 0, "format": fmt})
            kpis.append({"id": f"kpi:sum:{col.name}", "label": f"Total {col.name}",
                         "value": round(float(series.sum()), 2) if has else 0, "format": fmt})
            kpis.append({"id": f"kpi:max:{col.name}", "label": f"Max {col.name}",
                         "value": round(float(series.max()), 2) if has else 0, "format": fmt})
        return kpis

    def _chart_pool(self, df: pd.DataFrame, profile: DatasetProfile) -> list[dict]:
        numeric = [c for c in profile.columns if c.semantic_type in _NUMERIC]
        categorical = [
            c for c in profile.columns
            if c.semantic_type in _CATEGORICAL and 1 < c.distinct_count <= self.MAX_CATEGORIES
        ]
        temporal = [c for c in profile.columns if c.semantic_type in _TEMPORAL]
        measure = numeric[0].name if numeric else None

        pool: list[dict] = []
        # Category breakdowns (aggregated by the primary measure, plus counts).
        for cat in categorical[: self.POOL_CATEGORICAL]:
            if measure:
                ch = self._category_chart(df, cat.name, measure)
                ch["id"] = f"chart:{ch['type']}:{cat.name}:{measure}"
                pool.append(ch)
            ch2 = self._category_chart(df, cat.name, None)
            ch2["id"] = f"chart:{ch2['type']}:{cat.name}:count"
            pool.append(ch2)
        # Trends over time.
        for tcol in temporal[:2]:
            if numeric:
                ch = self._line_chart(df, tcol.name, numeric[0].name)
                ch["id"] = f"chart:line:{tcol.name}:{numeric[0].name}"
                pool.append(ch)
        # Scatter relationships between measures.
        for i in range(min(len(numeric) - 1, 3)):
            ch = self._scatter_chart(df, numeric[i].name, numeric[i + 1].name)
            ch["id"] = f"chart:scatter:{numeric[i].name}:{numeric[i + 1].name}"
            pool.append(ch)
        # Distributions of numeric columns.
        for col in numeric[:4]:
            ch = self._distribution_chart(df, col.name)
            ch["id"] = f"chart:hist:{col.name}"
            pool.append(ch)

        # Deduplicate by id and cap.
        seen: set[str] = set()
        out: list[dict] = []
        for ch in pool:
            if ch["id"] in seen or not ch["data"]:
                continue
            seen.add(ch["id"])
            out.append(ch)
            if len(out) >= self.POOL_MAX_CHARTS:
                break
        return out

    # ---- on-demand widget materialization (NL chart-on-command) ------ #
    # Derived from AGGREGATIONS so a KPI can compute anything a chart can —
    # keeping two separate lists is how "median revenue" ended up refused on the
    # KPI path while the chart path would have handled it.
    _KPI_LABELS = {
        "avg": "Avg", "sum": "Total", "median": "Median", "max": "Max", "min": "Min",
        "stddev": "Std dev of", "variance": "Variance of", "count": "Count of",
        "count_distinct": "Distinct",
    }

    def materialize_kpi(self, df: pd.DataFrame, profile: DatasetProfile, kpi_id: str) -> dict | None:
        """Build a KPI card from a compositional id like ``kpi:avg:price``."""
        parts = kpi_id.split(":", 2)
        if len(parts) != 3 or parts[0] != "kpi":
            # Dataset-level ids from the static pool.
            if kpi_id == "kpi:rows":
                return {"id": kpi_id, "label": "Total Rows", "value": profile.row_count, "format": "number"}
            if kpi_id == "kpi:cols":
                return {"id": kpi_id, "label": "Columns", "value": profile.col_count, "format": "number"}
            return None
        _, agg, col = parts
        if agg not in self.AGGREGATIONS or col not in df.columns:
            return None
        method, _word = self.AGGREGATIONS[agg]

        # Counting works on any column; the rest need numeric values.
        if agg == "count":
            value: float = int(df[col].notna().sum())
        elif agg == "count_distinct":
            value = int(df[col].nunique(dropna=True))
        else:
            series = pd.to_numeric(df[col], errors="coerce")
            if not series.notna().any():
                return None
            computed = getattr(series, method)()
            if computed is None or pd.isna(computed):
                return None  # e.g. stddev of a single value
            value = round(float(computed), 2)

        prof = next((c for c in profile.columns if c.name == col), None)
        # A count or a spread isn't money even when the column is.
        is_currency = prof and prof.semantic_type == SemanticType.CURRENCY
        fmt = "currency" if is_currency and agg not in {"count", "count_distinct"} else "number"
        return {
            "id": kpi_id,
            "label": f"{self._KPI_LABELS.get(agg, agg.title())} {col}",
            "value": value,
            "format": fmt,
        }

    @classmethod
    def _parse_measure(cls, token: str) -> tuple[str, str]:
        """Split ``"avg(revenue)"`` into ``("avg", "revenue")``.

        A bare ``"revenue"`` means SUM, which keeps chart ids created before
        aggregations were selectable valid.
        """
        match = re.fullmatch(r"(\w+)\((.+)\)", token.strip())
        if match and match.group(1).lower() in cls.AGGREGATIONS:
            return match.group(1).lower(), match.group(2).strip()
        return "sum", token

    def materialize_chart(self, df: pd.DataFrame, profile: DatasetProfile, chart_id: str) -> dict | None:
        """Build a chart spec from a compositional id like ``chart:bar:region:sales``."""
        parts = chart_id.split(":", 2)
        if len(parts) != 3 or parts[0] != "chart":
            return None
        _, chart_type, rest = parts
        try:
            if chart_type == "hist":
                if rest not in df.columns:
                    return None
                ch = self._distribution_chart(df, rest)
            else:
                x, y = rest.rsplit(":", 1)
                if x not in df.columns:
                    return None
                if chart_type == "line":
                    agg, column = self._parse_measure(y)
                    if column not in df.columns:
                        return None
                    ch = self._line_chart(df, x, column, agg)
                elif chart_type == "scatter":
                    if y not in df.columns:
                        return None
                    ch = self._scatter_chart(df, x, y)
                elif chart_type in {"bar", "pie"}:
                    # The measure may carry an aggregation, e.g. "avg(revenue)".
                    # A bare column name still means SUM, so ids saved before
                    # aggregations existed keep working unchanged.
                    agg, column = self._parse_measure(y)
                    measure = column if column != "count" and column in df.columns else None
                    if column != "count" and measure is None:
                        return None
                    ch = self._category_chart(df, x, measure, agg)
                    ch["type"] = chart_type  # honor the requested type
                else:
                    return None
        except (ValueError, TypeError, KeyError):
            return None
        if not ch["data"]:
            return None
        ch["id"] = chart_id
        return ch

    # ---- KPIs --------------------------------------------------------- #
    def _kpis(self, df: pd.DataFrame, profile: DatasetProfile) -> list[dict]:
        kpis = [
            {"label": "Total Rows", "value": profile.row_count, "format": "number"},
            {"label": "Columns", "value": profile.col_count, "format": "number"},
        ]
        numeric_cols = [c for c in profile.columns if c.semantic_type in _NUMERIC]
        for col in numeric_cols[:2]:
            series = pd.to_numeric(df[col.name], errors="coerce")
            fmt = "currency" if col.semantic_type == SemanticType.CURRENCY else "number"
            kpis.append({
                "label": f"Avg {col.name}",
                "value": round(float(series.mean()), 2) if series.notna().any() else 0,
                "format": fmt,
            })
        return kpis[:4]

    # ---- Charts ------------------------------------------------------- #
    def _charts(self, df: pd.DataFrame, profile: DatasetProfile) -> list[dict]:
        charts: list[dict] = []
        numeric = [c for c in profile.columns if c.semantic_type in _NUMERIC]
        categorical = [
            c for c in profile.columns
            if c.semantic_type in _CATEGORICAL and 1 < c.distinct_count <= self.MAX_CATEGORIES
        ]
        temporal = [c for c in profile.columns if c.semantic_type in _TEMPORAL]

        # Bar / pie: categorical breakdowns, optionally aggregated by a measure.
        measure = numeric[0].name if numeric else None
        for cat in categorical[:3]:
            charts.append(self._category_chart(df, cat.name, measure))

        # Line: a measure over a temporal axis.
        if temporal and numeric:
            charts.append(self._line_chart(df, temporal[0].name, numeric[0].name))

        # Scatter: relationship between two measures.
        if len(numeric) >= 2:
            charts.append(self._scatter_chart(df, numeric[0].name, numeric[1].name))

        # Histogram-ish bar for a lone numeric column.
        if numeric and not categorical:
            charts.append(self._distribution_chart(df, numeric[0].name))

        return charts[: self.MAX_CHARTS]

    # Aggregation -> (pandas method, caption word). The caption is what tells a
    # reader whether a bar is a total or an average.
    #
    # Anything pandas can compute over a grouped numeric series belongs here —
    # adding one is a single entry, so the planner isn't limited to a token set.
    # The caption is a template so each reads as English: "Total revenue" but
    # "Std deviation of revenue".
    AGGREGATIONS = {
        "sum": ("sum", "Total {m}"),
        "avg": ("mean", "Average {m}"),
        "median": ("median", "Median {m}"),
        "min": ("min", "Minimum {m}"),
        "max": ("max", "Maximum {m}"),
        "stddev": ("std", "Std deviation of {m}"),
        "variance": ("var", "Variance of {m}"),
        "count": ("count", "Number of {m} values"),
        "count_distinct": ("nunique", "Distinct {m} values"),
    }
    # Aggregations that are additive, so a tail can be rolled into "Other".
    # Averaging averages (or summing medians) would be meaningless.
    _ADDITIVE_AGGS = {"sum", "count"}

    def _category_chart(self, df, category: str, measure: str | None, agg: str = "sum") -> dict:
        total = len(df)
        notes: list[str] = []
        if measure:
            method, template = self.AGGREGATIONS.get(agg, self.AGGREGATIONS["sum"])
            caption = template.format(m=measure)
            values = pd.to_numeric(df[measure], errors="coerce")
            tmp = pd.DataFrame({category: df[category], measure: values}).dropna()
            used = len(tmp)
            if used < total:
                # Name the column actually responsible — "missing A or B" leaves
                # the user guessing which one cost them the rows.
                notes.append(
                    f"{total - used} of {total} rows were excluded: "
                    + self._missing_breakdown({category: int(df[category].isna().sum()),
                                               measure: int(values.isna().sum())})
                )
            grouped = getattr(tmp.groupby(category)[measure], method)()
            # A spread over a single-row group is undefined; NaN isn't valid JSON
            # and would render as a gap, so drop those groups and say so.
            undefined = int(grouped.isna().sum())
            if undefined:
                grouped = grouped.dropna()
                notes.append(
                    f"{undefined} '{category}' value(s) have too few rows for a "
                    f"{caption.lower()} and were left out."
                )
            groups = grouped.sort_values(ascending=False)
            # An "Other" bucket only makes sense for additive measures; summing
            # averages would be nonsense, so non-sum charts take the top N.
            if agg in self._ADDITIVE_AGGS:
                data = self._with_other_bucket(groups, category, notes, as_int=False)
            else:
                head = groups.head(self.MAX_CATEGORIES)
                if len(groups) > self.MAX_CATEGORIES:
                    notes.append(
                        f"'{category}' has {len(groups)} distinct values; showing the top "
                        f"{self.MAX_CATEGORIES} by {caption.lower()}."
                    )
                data = [{"name": str(k), "value": round(float(v), 2)} for k, v in head.items()]
            title = f"{caption} by {category}"
        else:
            used = int(df[category].notna().sum())
            if used < total:
                notes.append(f"{total - used} of {total} rows have no '{category}' and were excluded.")
            groups = df[category].value_counts()
            data = self._with_other_bucket(groups, category, notes, as_int=True)
            title = f"Count by {category}"
        if len(data) <= 1:
            notes.append(
                f"'{category}' has only one distinct value in the usable rows, so this chart "
                "shows a single bar and won't tell you much."
            )
        # Pie only for a small share breakdown (≤4 slices); bars scale better
        # and keep the dashboard from being all pies.
        chart_type = "pie" if len(data) <= 4 else "bar"
        return {
            "type": chart_type, "title": title, "x": "name", "y": "value", "data": data,
            # Axis labels name the column AND the aggregation: "revenue by
            # product" alone leaves the reader guessing whether the bars are a
            # total, an average or a count.
            "x_label": category,
            "y_label": (
                self.AGGREGATIONS.get(agg, self.AGGREGATIONS["sum"])[1].format(m=measure)
                if measure
                else "Number of rows"
            ),
            "meta": self._coverage(used, total, notes),
        }

    def _with_other_bucket(self, groups, category: str, notes: list[str], *, as_int: bool) -> list[dict]:
        """Chart the top categories and aggregate the rest into one "Other" bar.

        High-cardinality columns used to lose their tail silently. Rolling the
        remainder into a single bucket keeps the chart readable *and* keeps the
        totals honest — the bars still sum to the real total.
        """
        cast = (lambda v: int(v)) if as_int else (lambda v: round(float(v), 2))
        if len(groups) <= self.MAX_CATEGORIES:
            return [{"name": str(k), "value": cast(v)} for k, v in groups.items()]

        head = groups.head(self.MAX_CATEGORIES)
        tail = groups.iloc[self.MAX_CATEGORIES:]
        notes.append(
            f"'{category}' has {len(groups)} distinct values; the top {self.MAX_CATEGORIES} are "
            f"charted individually and the remaining {len(tail)} are grouped as "
            f"\"{self.OTHER_LABEL}\"."
        )
        data = [{"name": str(k), "value": cast(v)} for k, v in head.items()]
        data.append({"name": self.OTHER_LABEL, "value": cast(tail.sum())})
        return data

    @staticmethod
    def _missing_breakdown(missing_by_column: dict[str, int]) -> str:
        """Phrase naming which columns cost rows, skipping the blameless ones.

        Counts are per column, so a row missing both is counted under each.
        """
        parts = [f"{count} have no '{col}'" for col, count in missing_by_column.items() if count]
        return (" and ".join(parts) + ".") if parts else "some values could not be read."

    @staticmethod
    def _coverage(rows_used: int, rows_total: int, notes: list[str]) -> dict:
        """Provenance for a chart: how much of the data actually made it in."""
        return {"rows_used": int(rows_used), "rows_total": int(rows_total), "notes": notes}

    def _line_chart(self, df, time_col: str, measure: str, agg: str = "sum") -> dict:
        total = len(df)
        method, template = self.AGGREGATIONS.get(agg, self.AGGREGATIONS["sum"])
        caption = template.format(m=measure)
        dates = parse_dates(df[time_col])
        values = pd.to_numeric(df[measure], errors="coerce")

        notes: list[str] = []
        unparsed = int(dates.isna().sum())
        if unparsed:
            notes.append(
                f"{unparsed} of {total} rows have a '{time_col}' value that isn't a recognisable "
                "date and were excluded."
            )
        non_numeric = int(values.isna().sum())
        if non_numeric:
            notes.append(f"{non_numeric} of {total} rows have no numeric '{measure}' and were excluded.")

        tmp = pd.DataFrame({time_col: dates, measure: values}).dropna().sort_values(time_col)
        grouped = getattr(tmp.groupby(tmp[time_col].dt.to_period("M"))[measure], method)()
        data = [{"name": str(k), "value": round(float(v), 2)} for k, v in grouped.items()]
        if len(data) == 1:
            notes.append(
                "Every usable row falls in a single month, so the trend is one point — "
                "check whether the date column parsed correctly."
            )
        return {
            "type": "line", "title": f"{caption} by month", "x": "name", "y": "value",
            "x_label": "Month", "y_label": caption, "data": data,
            "meta": self._coverage(len(tmp), total, notes),
        }

    def _scatter_chart(self, df, x: str, y: str) -> dict:
        total = len(df)
        xs = pd.to_numeric(df[x], errors="coerce")
        ys = pd.to_numeric(df[y], errors="coerce")
        tmp = pd.DataFrame({"x": xs, "y": ys}).dropna()
        usable = len(tmp)

        notes: list[str] = []
        if usable < total:
            notes.append(
                f"{total - usable} of {total} rows were excluded: "
                + self._missing_breakdown({
                    x: int(pd.to_numeric(df[x], errors="coerce").isna().sum()),
                    y: int(pd.to_numeric(df[y], errors="coerce").isna().sum()),
                })
            )
        if usable > self.MAX_SCATTER_POINTS:
            # Evenly spaced across the whole frame, not the first N rows — on
            # data sorted by either axis, head() would show one corner only.
            step = usable // self.MAX_SCATTER_POINTS + 1
            tmp = tmp.iloc[::step]
            notes.append(
                f"Plotting an evenly spaced sample of {len(tmp):,} points drawn from all "
                f"{usable:,} usable rows."
            )
        data = [{"x": float(a), "y": float(b)} for a, b in zip(tmp["x"], tmp["y"])]
        return {
            "type": "scatter", "title": f"{x} vs {y}", "x": "x", "y": "y",
            "x_label": x, "y_label": y, "data": data,
            "meta": self._coverage(usable, total, notes),
        }

    def _distribution_chart(self, df, col: str) -> dict:
        total = len(df)
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        notes: list[str] = []
        if len(series) < total:
            notes.append(f"{total - len(series)} of {total} rows have no numeric '{col}' and were excluded.")

        binned = pd.cut(series, bins=min(10, max(series.nunique(), 1)))
        counts = binned.value_counts().sort_index()
        data = [{"name": str(k), "value": int(v)} for k, v in counts.items()]
        return {
            "type": "bar", "title": f"Distribution of {col}", "x": "name", "y": "value",
            "x_label": f"{col} range", "y_label": "Number of rows", "data": data,
            "meta": self._coverage(len(series), total, notes),
        }
