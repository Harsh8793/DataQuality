"""Integration tests for the auth + dataset API flow."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _auth_headers() -> dict[str, str]:
    # Register a throwaway user (unique email via a counter file is overkill for
    # a hackathon; rely on login of the seeded demo user instead).
    res = client.post("/api/v1/auth/login", json={"email": "demo@datapilot.ai", "password": "demo1234"})
    if res.status_code != 200:
        client.post("/api/v1/auth/register", json={"name": "Test", "email": "demo@datapilot.ai", "password": "demo1234"})
        res = client.post("/api/v1/auth/login", json={"email": "demo@datapilot.ai", "password": "demo1234"})
    token = res.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health() -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "healthy"


def test_upload_and_analyze_flow() -> None:
    headers = _auth_headers()
    csv = b"name,email,amount\nAlice,a@x.com,10\nBob,bad@@,20\nAlice,a@x.com,10\n"
    upload = client.post(
        "/api/v1/datasets",
        headers=headers,
        files={"file": ("tiny.csv", io.BytesIO(csv), "text/csv")},
    )
    assert upload.status_code == 200
    dataset_id = upload.json()["data"]["id"]

    quality = client.get(f"/api/v1/datasets/{dataset_id}/quality", headers=headers)
    assert quality.status_code == 200
    assert 0 <= quality.json()["data"]["overall_score"] <= 100


def test_requires_auth() -> None:
    res = client.get("/api/v1/datasets")
    assert res.status_code == 401
