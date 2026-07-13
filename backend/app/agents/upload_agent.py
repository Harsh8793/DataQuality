"""Upload agent: detect format/encoding/delimiter and load raw bytes."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.base import Agent, AgentContext, AgentResult
from app.core.engines.loader import DataLoader, LoadResult


@dataclass
class UploadInput:
    """Input payload for the upload agent."""

    content: bytes
    extension: str


class UploadAgent(Agent):
    """Loads an uploaded file into a DataFrame with detected metadata."""

    name = "upload"

    def __init__(self) -> None:
        super().__init__()
        self._loader = DataLoader()

    def load(self, content: bytes, extension: str) -> LoadResult:
        """Load raw bytes into a :class:`LoadResult` (used before a context exists)."""
        return self._loader.load(content, extension)

    def run(self, ctx: AgentContext) -> AgentResult:
        """Load bytes present in ``ctx.meta['upload']`` into ``ctx.df``."""
        payload: UploadInput | None = ctx.meta.get("upload")
        if payload is None:
            return self._fail("No upload payload provided.")
        result = self._loader.load(payload.content, payload.extension)
        ctx.df = result.df
        ctx.meta["load_result"] = result
        return self._ok({"format": result.file_format, "rows": len(result.df)})
