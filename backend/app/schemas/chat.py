"""Chat, dashboard, governance and insight schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---- Chat ------------------------------------------------------------- #
class ChatRequest(BaseModel):
    """A natural-language question about a dataset."""

    question: str = Field(min_length=1, max_length=500)
    session_id: int | None = None


class ChatResponse(BaseModel):
    """The assistant's answer with SQL, tabular result and optional chart."""

    answer: str
    sql: str
    columns: list[str]
    rows: list[dict]
    row_count: int
    chart_spec: dict | None = None
    session_id: int


class ChatHistoryMessage(BaseModel):
    """A persisted chat turn returned when restoring history."""

    role: str
    content: str
    sql: str | None = None
    columns: list[str] = []
    rows: list[dict] = []
    chart_spec: dict | None = None


class ChatHistoryResponse(BaseModel):
    """The most recent chat session's messages for a dataset."""

    session_id: int | None = None
    messages: list[ChatHistoryMessage] = []


# ---- Dashboard -------------------------------------------------------- #
class KpiCard(BaseModel):
    """A single KPI tile."""

    id: str | None = None
    label: str
    value: float | int
    format: str = "number"


class ChartSpec(BaseModel):
    """A chart specification consumed by the frontend renderer."""

    id: str | None = None
    type: str
    title: str
    x: str
    y: str
    data: list[dict]


class DashboardResponse(BaseModel):
    """Auto-generated dashboard specification."""

    kpis: list[KpiCard]
    charts: list[ChartSpec]


class WidgetPool(BaseModel):
    """The full set of addable widgets for the dashboard builder."""

    kpis: list[KpiCard]
    charts: list[ChartSpec]


class DashboardSelection(BaseModel):
    """Selected widget ids for a user's custom dashboard."""

    kpis: list[str]
    charts: list[str]


class DashboardBuilderResponse(BaseModel):
    """Everything the dashboard builder needs: the pool plus the selection."""

    pool: WidgetPool
    selected: DashboardSelection


class SaveDashboardRequest(BaseModel):
    """Persist a user's selected widget ids."""

    kpis: list[str]
    charts: list[str]


# ---- Governance ------------------------------------------------------- #
class GovernanceResponse(BaseModel):
    """Governance classification and ingestion recommendation."""

    classification: str
    pii_columns: list[str]
    rationale: str | None = None
    ingestion_tier: str
    tier_rationale: str | None = None
    column_metadata: list[dict] = []

    model_config = {"from_attributes": True}


# ---- Insights --------------------------------------------------------- #
class InsightItem(BaseModel):
    """A single business insight."""

    title: str
    insight: str
    action: str
    category: str


# ---- Reports ---------------------------------------------------------- #
class ReportRequest(BaseModel):
    """Request to generate an export artifact."""

    report_type: str = Field(pattern="^(pdf|xlsx|json|csv)$")


class ReportResponse(BaseModel):
    """Metadata for a generated report."""

    id: int
    report_type: str
    title: str
    size_bytes: int

    model_config = {"from_attributes": True}
