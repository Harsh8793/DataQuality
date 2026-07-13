"""Seed the database with a demo user and a pre-analyzed messy dataset.

Run once for an instant-on demo:  python -m scripts.seed
"""

from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger
from app.database.init_db import init_db
from app.database.session import session_scope
from app.schemas.auth import RegisterRequest
from app.services.analysis_service import AnalysisService
from app.services.auth_service import AuthService
from app.services.dataset_service import DatasetService
from scripts.generate_samples import main as generate_samples

logger = get_logger("seed")

DEMO_EMAIL = "demo@datapilot.ai"
DEMO_PASSWORD = "demo1234"
SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "messy_sales.csv"


def seed() -> None:
    """Create tables, a demo user, and upload+analyze the sample dataset."""
    init_db()
    if not SAMPLE.exists():
        generate_samples()

    with session_scope() as db:
        auth = AuthService(db)
        user = auth.users.get_by_email(DEMO_EMAIL)
        if user is None:
            token = auth.register(RegisterRequest(name="Demo Analyst", email=DEMO_EMAIL, password=DEMO_PASSWORD))
            user_id = token.user.id
            logger.info("Created demo user %s", DEMO_EMAIL)
        else:
            user_id = user.id
            logger.info("Demo user already exists")

        # Only seed the dataset once.
        existing, _ = DatasetService(db).list(user_id, limit=1, offset=0)
        if existing:
            logger.info("Demo dataset already present, skipping upload.")
            return

        content = SAMPLE.read_bytes()
        summary = DatasetService(db).upload(user_id, "messy_sales.csv", content)
        logger.info("Uploaded demo dataset %s", summary.id)
        report = AnalysisService(db).analyze(summary.id, user_id)
        logger.info("Analyzed demo dataset: score %s/100", report.overall_score)

    print("\nSeed complete.")
    print(f"  Login: {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    seed()
