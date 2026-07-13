"""Auto-dashboard and insights endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.insight_agent import InsightAgent
from app.agents.profiling_agent import ProfilingAgent
from app.agents.quality_agent import QualityAgent
from app.database.session import get_db
from app.dependencies.auth import CurrentUser
from app.schemas.ai import ChartCommandRequest, ChartCommandResponse
from app.schemas.chat import (
    DashboardBuilderResponse,
    InsightItem,
    SaveDashboardRequest,
)
from app.schemas.common import ApiResponse
from app.services.base import BaseService, DatasetContextMixin
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/datasets", tags=["Dashboard & Insights"])


class _InsightRunner(BaseService, DatasetContextMixin):
    """Small service wrapper to run insight generation for the endpoint."""

    def run(self, dataset_id: int, user_id: int) -> list[dict]:
        dataset = self._load_owned_dataset(dataset_id, user_id)
        ctx = self._build_context(dataset)
        ProfilingAgent().run(ctx)
        QualityAgent().run(ctx)
        return InsightAgent().generate_insights(ctx)


@router.get("/{dataset_id}/dashboard", response_model=ApiResponse[DashboardBuilderResponse])
def get_dashboard(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Return the dashboard widget pool plus the user's saved/default selection."""
    return ApiResponse.ok(DashboardService(db).get_builder(dataset_id, current_user.id))


@router.put("/{dataset_id}/dashboard", response_model=ApiResponse[None])
def save_dashboard(
    dataset_id: int,
    payload: SaveDashboardRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Persist the user's custom dashboard widget selection."""
    DashboardService(db).save_selection(dataset_id, current_user.id, payload.kpis, payload.charts)
    return ApiResponse.ok(message="Dashboard saved.")


@router.post("/{dataset_id}/dashboard/command", response_model=ApiResponse[ChartCommandResponse])
def dashboard_command(
    dataset_id: int,
    payload: ChartCommandRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Create a KPI or chart from a natural-language command (AI-planned)."""
    result = DashboardService(db).command(dataset_id, current_user.id, payload.command)
    return ApiResponse.ok(result, message=result.message)


@router.get("/{dataset_id}/insights", response_model=ApiResponse[list[InsightItem]])
def get_insights(dataset_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Return AI-generated business insights for a dataset."""
    insights = _InsightRunner(db).run(dataset_id, current_user.id)
    items = [InsightItem(**i) for i in insights if {"title", "insight", "action", "category"} <= set(i)]
    return ApiResponse.ok(items)
