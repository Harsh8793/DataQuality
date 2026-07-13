"""Filesystem storage abstraction for uploads, parquet caches and reports.

Centralizes path handling and guards against path-traversal so callers never
build filesystem paths by hand.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: str) -> str:
    """Strip unsafe characters from a filename to prevent path traversal."""
    cleaned = _SAFE_NAME.sub("_", Path(name).name).strip("._")
    return cleaned or "file"


class StorageService:
    """Manages physical files on disk for the application."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._settings.ensure_directories()

    # ---- directories -------------------------------------------------- #
    @property
    def upload_dir(self) -> Path:
        return self._settings.resolve(self._settings.upload_dir)

    @property
    def parquet_dir(self) -> Path:
        return self._settings.resolve(self._settings.parquet_dir)

    @property
    def report_dir(self) -> Path:
        return self._settings.resolve(self._settings.report_dir)

    # ---- write helpers ------------------------------------------------ #
    def save_upload(self, original_filename: str, content: bytes) -> tuple[str, Path]:
        """Persist raw upload bytes under a unique, sanitized filename.

        Returns the stored filename and its absolute path.
        """
        safe = sanitize_filename(original_filename)
        unique = f"{uuid.uuid4().hex}_{safe}"
        target = self.upload_dir / unique
        target.write_bytes(content)
        logger.info("Saved upload '%s' (%d bytes)", unique, len(content))
        return unique, target

    def parquet_path(self, dataset_id: str) -> Path:
        """Absolute path where a dataset's parquet cache is stored."""
        return self.parquet_dir / f"{dataset_id}.parquet"

    def report_path(self, filename: str) -> Path:
        """Absolute path for a generated report artifact."""
        return self.report_dir / sanitize_filename(filename)


_storage: StorageService | None = None


def get_storage() -> StorageService:
    """Return a process-wide :class:`StorageService` singleton."""
    global _storage
    if _storage is None:
        _storage = StorageService()
    return _storage
