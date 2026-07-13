"""Governance service: classify sensitivity and recommend an ingestion tier."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.governance_agent import GovernanceAgent
from app.agents.profiling_agent import ProfilingAgent
from app.agents.quality_agent import QualityAgent
from app.repositories.governance_repository import GovernanceRepository
from app.schemas.chat import GovernanceResponse
from app.services.base import BaseService, DatasetContextMixin


class GovernanceService(BaseService, DatasetContextMixin):
    """Produces or retrieves a dataset's governance classification."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.profiling_agent = ProfilingAgent()
        self.quality_agent = QualityAgent()
        self.governance_agent = GovernanceAgent()
        self.governance = GovernanceRepository(db)

    def classify(self, dataset_id: str, user_id: str) -> GovernanceResponse:
        """Run governance classification for a dataset."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        ctx = self._build_context(dataset)
        ctx.meta["is_cleaned"] = dataset.is_cleaned
        self.profiling_agent.run(ctx)
        self.quality_agent.run(ctx)
        result = self.governance_agent.classify(ctx)

        self.governance.create(
            dataset_id=dataset_id, user_id=user_id, classification=result.classification,
            pii_columns=result.pii_columns, rationale=result.rationale,
            ingestion_tier=result.ingestion_tier, tier_rationale=result.tier_rationale,
            created_by=user_id,
        )
        self.db.commit()
        return GovernanceResponse(
            classification=result.classification, pii_columns=result.pii_columns,
            rationale=result.rationale, ingestion_tier=result.ingestion_tier,
            tier_rationale=result.tier_rationale, column_metadata=result.column_metadata,
        )
