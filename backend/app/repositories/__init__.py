"""Repository layer: the only place that talks to the ORM/database."""

from app.repositories.analysis_repository import (
    AnalysisHistoryRepository,
    QualityIssueRepository,
    QualityReportRepository,
)
from app.repositories.base import BaseRepository
from app.repositories.chat_repository import ChatMessageRepository, ChatSessionRepository
from app.repositories.cleaning_repository import CleaningRepository
from app.repositories.dataset_repository import (
    DatasetColumnRepository,
    DatasetRepository,
    UploadedFileRepository,
)
from app.repositories.governance_repository import GovernanceRepository
from app.repositories.report_repository import DashboardRepository, ReportRepository
from app.repositories.user_repository import UserRepository

__all__ = [
    "BaseRepository",
    "UserRepository",
    "UploadedFileRepository",
    "DatasetRepository",
    "DatasetColumnRepository",
    "QualityReportRepository",
    "QualityIssueRepository",
    "AnalysisHistoryRepository",
    "ChatSessionRepository",
    "ChatMessageRepository",
    "CleaningRepository",
    "GovernanceRepository",
    "ReportRepository",
    "DashboardRepository",
]
