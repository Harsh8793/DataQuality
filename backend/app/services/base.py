"""Base service and shared dataset helpers."""

from __future__ import annotations

import pandas as pd
from sqlalchemy.orm import Session

from app.agents.base import AgentContext
from app.core.logging import get_logger
from app.exceptions.base import DatasetNotFoundException
from app.models.dataset import Dataset
from app.repositories.dataset_repository import DatasetRepository


class BaseService:
    """Base class that gives every service a db session and logger."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.logger = get_logger(f"service.{self.__class__.__name__}")


class DatasetContextMixin:
    """Helpers to load a dataset frame and build an :class:`AgentContext`."""

    db: Session

    def _load_owned_dataset(self, dataset_id: int, user_id: int) -> Dataset:
        """Return an owned dataset or raise :class:`DatasetNotFoundException`."""
        dataset = DatasetRepository(self.db).get_owned(dataset_id, user_id)
        if dataset is None:
            raise DatasetNotFoundException("Dataset not found.")
        return dataset

    @staticmethod
    def _read_frame(dataset: Dataset) -> pd.DataFrame:
        """Load a dataset's parquet cache into a DataFrame."""
        return pd.read_parquet(dataset.parquet_path)

    def _build_context(self, dataset: Dataset) -> AgentContext:
        """Construct an :class:`AgentContext` for pipeline/agent execution."""
        df = self._read_frame(dataset)
        return AgentContext(dataset_id=dataset.id, dataset_name=dataset.name, df=df)
