"""SQLAlchemy engine and session management."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _resolve_database_url() -> str:
    """Resolve the database URL, making SQLite paths absolute and their dir exist.

    The engine is created at import time, so we must guarantee the target
    directory exists and the path is independent of the process CWD.
    """
    settings = get_settings()
    url = settings.database_url
    prefix = "sqlite:///"
    if url.startswith(prefix):
        raw_path = url[len(prefix):]
        abs_path = settings.resolve(raw_path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        return f"{prefix}{abs_path.as_posix()}"
    return url


_settings = get_settings()
_database_url = _resolve_database_url()

# ``check_same_thread`` is required for SQLite when used across FastAPI threads.
_connect_args = {"check_same_thread": False} if _database_url.startswith("sqlite") else {}

engine = create_engine(
    _database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context-managed session that commits on success and rolls back on error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
