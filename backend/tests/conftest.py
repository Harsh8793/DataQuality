"""Shared fixtures for the tab test-suites.

Every test here runs against a temporary SQLite database and a stubbed LLM, so
the suite is deterministic, offline and safe to run in CI. The stub is the
important part: the product is built so the deterministic engines carry the
answer and the LLM only garnishes it, and these tests hold that line by
asserting the engines behave correctly with no model available at all.
"""

from __future__ import annotations

import io
from collections.abc import Iterator

import pandas as pd
import pytest

import app.core.llm.groq_client as groq_client


# --------------------------------------------------------------------------- #
# LLM stubbing
# --------------------------------------------------------------------------- #
class StubLLM:
    """Stand-in for :class:`GroqLLM` with scripted, inspectable responses.

    ``available`` defaults to ``False`` so tests exercise the deterministic
    fallbacks unless they explicitly opt into a scripted reply.
    """

    def __init__(self, *, available: bool = False, text: str | None = None, payload=None) -> None:
        self.available = available
        self._text = text
        self._payload = payload
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, *, temperature: float | None = None) -> str | None:
        self.calls.append((system, user))
        return self._text

    def complete_json(self, system: str, user: str):
        self.calls.append((system, user))
        return self._payload

    def stream(self, system: str, user: str):
        self.calls.append((system, user))
        yield from ()

    @property
    def health(self):
        return groq_client.LlmHealth(
            status=groq_client.LlmStatus.DISABLED, model="stub", detail="stubbed for tests"
        )


@pytest.fixture(autouse=True)
def stub_llm(monkeypatch: pytest.MonkeyPatch) -> StubLLM:
    """Replace the process-wide LLM singleton for every test.

    Autouse so a forgotten patch can never turn a unit test into a live Groq
    call (slow, costly and non-deterministic).
    """
    stub = StubLLM()
    monkeypatch.setattr(groq_client, "_llm", stub)
    monkeypatch.setattr(groq_client, "get_llm", lambda: stub)
    # Modules that imported the symbol directly need patching at their own site.
    for module in (
        "app.core.llm",
        "app.agents.chat_agent",
        "app.agents.governance_agent",
        "app.agents.insight_agent",
        "app.services.dashboard_service",
        "app.services.analysis_service",
    ):
        try:
            monkeypatch.setattr(f"{module}.get_llm", lambda: stub, raising=False)
        except AttributeError:  # pragma: no cover - module without the symbol
            pass
    return stub


def scripted_llm(monkeypatch: pytest.MonkeyPatch, **kwargs) -> StubLLM:
    """Install a stub that answers with the given text/payload."""
    stub = StubLLM(available=True, **kwargs)
    monkeypatch.setattr(groq_client, "_llm", stub)
    monkeypatch.setattr(groq_client, "get_llm", lambda: stub)
    for module in (
        "app.core.llm",
        "app.agents.chat_agent",
        "app.agents.governance_agent",
        "app.agents.insight_agent",
        "app.services.dashboard_service",
        "app.services.analysis_service",
    ):
        monkeypatch.setattr(f"{module}.get_llm", lambda: stub, raising=False)
    return stub


# --------------------------------------------------------------------------- #
# Sample data
# --------------------------------------------------------------------------- #
@pytest.fixture
def messy_frame() -> pd.DataFrame:
    """A deliberately dirty frame covering the failure modes we handle.

    Mixed date formats, inconsistent casing, nulls, duplicates, whitespace and
    an unparseable value — the shapes that produced wrong answers in practice.
    """
    return pd.DataFrame(
        {
            "customer_id": [1, 2, 3, 4, 5, 6, 6],
            "name": ["  Ann  ", "Bob", "Cara", "Dan", None, "Eve", "Eve"],
            "email": ["a@x.com", "bad@@", "c@x.com", None, "e@x.com", "f@x.com", "f@x.com"],
            "state": ["California", "california", "Texas", "TEXAS", "Ohio", None, None],
            "gender": ["m", "M", "male", "f", "F", "female", "female"],
            "product": ["Laptop", "Laptop", "Mouse", "Mouse", "Webcam", "Mouse", "Mouse"],
            "revenue": [100.0, 200.0, None, 400.0, 500.0, 600.0, 600.0],
            "quantity": [1, 2, 3, 4, 5, 6, 6],
            "order_date": [
                "15/02/2024", "2024-04-10", "2024/03/20", "not a date",
                "2024-02-28", "01/05/2024", "01/05/2024",
            ],
        }
    )


@pytest.fixture
def clean_frame() -> pd.DataFrame:
    """A small, entirely clean frame for happy-path assertions."""
    return pd.DataFrame(
        {
            "region": ["North", "South", "North", "East"],
            "sales": [10.0, 20.0, 30.0, 40.0],
            "units": [1, 2, 3, 4],
            "sold_on": ["2024-01-05", "2024-02-05", "2024-03-05", "2024-04-05"],
        }
    )


@pytest.fixture
def messy_csv_bytes(messy_frame: pd.DataFrame) -> bytes:
    buffer = io.StringIO()
    messy_frame.to_csv(buffer, index=False)
    return buffer.getvalue().encode()


# --------------------------------------------------------------------------- #
# Database + API client
# --------------------------------------------------------------------------- #
@pytest.fixture
def db_session() -> Iterator:
    """A transactional session on the app's configured database.

    Everything written is rolled back, so tests never leave rows behind.
    """
    from app.database.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="session")
def client():
    """TestClient bound to the real app (integration-level assertions)."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def auth_headers(client) -> dict[str, str]:
    """Bearer headers for the seeded demo user, registering it if absent."""
    credentials = {"email": "demo@datapilot.ai", "password": "demo1234"}
    res = client.post("/api/v1/auth/login", json=credentials)
    if res.status_code != 200:
        client.post("/api/v1/auth/register", json={"name": "Test", **credentials})
        res = client.post("/api/v1/auth/login", json=credentials)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}
