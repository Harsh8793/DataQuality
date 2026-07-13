"""Thin, resilient wrapper around the Groq chat completions API.

The wrapper is intentionally defensive: if the LLM is disabled or a call
fails, callers receive ``None`` (or a fallback) instead of an exception, so the
deterministic core of the product keeps working during a live demo.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)


class GroqLLM:
    """Wrapper providing text, JSON and streaming completions."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = None
        if self._settings.is_llm_ready:
            try:
                from groq import Groq

                self._client = Groq(api_key=self._settings.groq_api_key)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Groq client init failed, LLM disabled: %s", exc)

    @property
    def available(self) -> bool:
        """Whether live LLM calls can be made."""
        return self._client is not None

    # ---- completions -------------------------------------------------- #
    def complete(self, system: str, user: str, *, temperature: float | None = None) -> str | None:
        """Return a text completion, or ``None`` if the LLM is unavailable."""
        if not self.available:
            return None
        try:
            resp = self._client.chat.completions.create(
                model=self._settings.groq_model,
                temperature=self._settings.llm_temperature if temperature is None else temperature,
                max_tokens=self._settings.llm_max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return resp.choices[0].message.content
        except Exception as exc:  # noqa: BLE001 - never break the pipeline
            logger.warning("LLM completion failed: %s", exc)
            return None

    def complete_json(self, system: str, user: str) -> Any | None:
        """Return a parsed JSON completion, or ``None`` on failure."""
        raw = self.complete(
            system + "\nRespond ONLY with valid minified JSON. No prose, no markdown fences.",
            user,
            temperature=0.1,
        )
        if raw is None:
            return None
        return self._parse_json(raw)

    def stream(self, system: str, user: str) -> Iterator[str]:
        """Yield completion tokens as they arrive (empty iterator if unavailable)."""
        if not self.available:
            return
        try:
            stream = self._client.chat.completions.create(
                model=self._settings.groq_model,
                temperature=self._settings.llm_temperature,
                max_tokens=self._settings.llm_max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM stream failed: %s", exc)
            return

    @staticmethod
    def _parse_json(raw: str) -> Any | None:
        """Extract and parse the first JSON object/array from a model response."""
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = _JSON_BLOCK.search(raw)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    return None
        return None


_llm: GroqLLM | None = None


def get_llm() -> GroqLLM:
    """Return a process-wide :class:`GroqLLM` singleton."""
    global _llm
    if _llm is None:
        _llm = GroqLLM()
    return _llm
