"""Chart recommendation engine: derive dashboard specs from a profile.

The backend decides *what* to chart (spec); the frontend decides *how* to
render it. Specs are plain dicts so they serialize directly to JSON.
"""

from __future__ import annotations

import pandas as pd

from app.constants.enums import SemanticType
from app.core.engines.profiler import DatasetProfile

_NUMERIC = {SemanticType.NUMERIC, SemanticType.INTEGER, SemanticType.CURRENCY}
_CATEGORICAL = {SemanticType.CATEGORICAL, SemanticType.TEXT, SemanticType.BOOLEAN}
_TEMPORAL = {SemanticType.DATE, SemanticType.DATETIME}


class ChartRecommender:
    """Builds KPI cards and chart specifications for a dataset."""

    MAX_CHARTS = 6
    MAX_CATEGORIES = 12

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
    _KPI_AGGS = {"avg": "mean", "sum": "sum", "max": "max", "min": "min", "count": "count"}

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
        if agg not in self._KPI_AGGS or col not in df.columns:
            return None
        series = pd.to_numeric(df[col], errors="coerce")
        if agg == "count":
            value: float = int(df[col].notna().sum())
        elif not series.notna().any():
            return None
        else:
            value = round(float(getattr(series, self._KPI_AGGS[agg])()), 2)
        prof = next((c for c in profile.columns if c.name == col), None)
        fmt = "currency" if prof and prof.semantic_type == SemanticType.CURRENCY else "number"
        label = {"avg": f"Avg {col}", "sum": f"Total {col}", "max": f"Max {col}",
                 "min": f"Min {col}", "count": f"Count of {col}"}[agg]
        return {"id": kpi_id, "label": label, "value": value, "format": fmt}

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
                    if y not in df.columns:
                        return None
                    ch = self._line_chart(df, x, y)
                elif chart_type == "scatter":
                    if y not in df.columns:
                        return None
                    ch = self._scatter_chart(df, x, y)
                elif chart_type in {"bar", "pie"}:
                    measure = y if y != "count" and y in df.columns else None
                    if y != "count" and measure is None:
                        return None
                    ch = self._category_chart(df, x, measure)
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

    def _category_chart(self, df, category: str, measure: str | None) -> dict:
        if measure:
            tmp = pd.DataFrame({category: df[category], measure: pd.to_numeric(df[measure], errors="coerce")}).dropna()
            grouped = (
                tmp.groupby(category)[measure]
                .sum()
                .sort_values(ascending=False)
                .head(self.MAX_CATEGORIES)
            )
            data = [{"name": str(k), "value": round(float(v), 2)} for k, v in grouped.items()]
            title = f"{measure} by {category}"
        else:
            counts = df[category].value_counts().head(self.MAX_CATEGORIES)
            data = [{"name": str(k), "value": int(v)} for k, v in counts.items()]
            title = f"Count by {category}"
        # Pie only for a small share breakdown (≤4 slices); bars scale better
        # and keep the dashboard from being all pies.
        chart_type = "pie" if len(data) <= 4 else "bar"
        return {"type": chart_type, "title": title, "x": "name", "y": "value", "data": data}

    def _line_chart(self, df, time_col: str, measure: str) -> dict:
        tmp = pd.DataFrame({
            time_col: pd.to_datetime(df[time_col], errors="coerce"),
            measure: pd.to_numeric(df[measure], errors="coerce"),
        }).dropna().sort_values(time_col)
        grouped = tmp.groupby(tmp[time_col].dt.to_period("M"))[measure].sum()
        data = [{"name": str(k), "value": round(float(v), 2)} for k, v in grouped.items()]
        return {"type": "line", "title": f"{measure} over time", "x": "name", "y": "value", "data": data}

    def _scatter_chart(self, df, x: str, y: str) -> dict:
        tmp = pd.DataFrame({
            "x": pd.to_numeric(df[x], errors="coerce"),
            "y": pd.to_numeric(df[y], errors="coerce"),
        }).dropna().head(300)
        data = [{"x": float(a), "y": float(b)} for a, b in zip(tmp["x"], tmp["y"])]
        return {"type": "scatter", "title": f"{x} vs {y}", "x": "x", "y": "y", "data": data}

    def _distribution_chart(self, df, col: str) -> dict:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        binned = pd.cut(series, bins=min(10, max(series.nunique(), 1)))
        counts = binned.value_counts().sort_index()
        data = [{"name": str(k), "value": int(v)} for k, v in counts.items()]
        return {"type": "bar", "title": f"Distribution of {col}", "x": "name", "y": "value", "data": data}
