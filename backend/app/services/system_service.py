"""System status service.

Unlike the other services this one touches no database — it reports on
process-level health (currently the LLM layer), so it takes no session.
"""

from __future__ import annotations

from app.constants.enums import LlmStatus
from app.core.llm.groq_client import get_llm
from app.core.logging import get_logger
from app.schemas.system import LlmStatusResponse

# Short, demo-friendly wording for the dashboard tile.
_LLM_LABELS: dict[LlmStatus, str] = {
    LlmStatus.ACTIVE: "Active",
    LlmStatus.DEGRADED: "Degraded",
    LlmStatus.UNCONFIGURED: "Not configured",
    LlmStatus.DISABLED: "Disabled",
}


class SystemService:
    """Read-only view of runtime health for the frontend."""

    def __init__(self) -> None:
        self.logger = get_logger(f"service.{self.__class__.__name__}")

    def llm_status(self) -> LlmStatusResponse:
        """Return the current health of the LLM layer."""
        health = get_llm().health
        return LlmStatusResponse(
            status=health.status,
            label=_LLM_LABELS[health.status],
            model=health.model,
            detail=health.detail,
            healthy=health.status is LlmStatus.ACTIVE,
            last_success_at=health.last_success_at,
            last_error_at=health.last_error_at,
        )
