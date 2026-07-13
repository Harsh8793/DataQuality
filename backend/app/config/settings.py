"""Centralized, environment-driven application settings.

All configuration is loaded from environment variables (via a local ``.env``
file in development). Nothing here should ever be hardcoded in business code -
inject :class:`Settings` through :func:`get_settings` instead.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to the ``backend/`` directory so relative storage paths resolve
# consistently regardless of the process working directory.
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Strongly-typed application settings sourced from the environment."""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ----
    app_name: str = "DataPilot AI"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # ---- CORS ----
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"

    # ---- Security / JWT ----
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # ---- Database ----
    database_url: str = "sqlite:///./data/datapilot.db"

    # ---- Storage ----
    data_dir: str = "./data"
    upload_dir: str = "./data/uploads"
    parquet_dir: str = "./data/parquet"
    report_dir: str = "./data/reports"
    chroma_dir: str = "./data/chroma"

    # ---- Upload limits ----
    max_upload_mb: int = 50
    allowed_extensions: str = "csv,xlsx,xls,json"

    # ---- LLM ----
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1500
    llm_enabled: bool = True

    # ------------------------------------------------------------------ #
    # Derived / normalized values
    # ------------------------------------------------------------------ #
    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins parsed into a clean list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_extension_set(self) -> set[str]:
        """Allowed upload extensions (lowercase, no dot)."""
        return {e.strip().lower().lstrip(".") for e in self.allowed_extensions.split(",") if e.strip()}

    @property
    def max_upload_bytes(self) -> int:
        """Maximum upload size expressed in bytes."""
        return self.max_upload_mb * 1024 * 1024

    def resolve(self, relative: str) -> Path:
        """Resolve a possibly-relative path against the backend root."""
        path = Path(relative)
        return path if path.is_absolute() else (BACKEND_ROOT / path).resolve()

    @property
    def is_llm_ready(self) -> bool:
        """Whether the LLM layer can be used (enabled and key present)."""
        return self.llm_enabled and bool(self.groq_api_key)

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    def ensure_directories(self) -> None:
        """Create all runtime storage directories if they do not exist."""
        for path in (self.data_dir, self.upload_dir, self.parquet_dir, self.report_dir, self.chroma_dir):
            self.resolve(path).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return a cached, process-wide :class:`Settings` instance."""
    return Settings()
