"""Database initialization: create all tables.

Importing :mod:`app.models` registers every table on the shared ``Base``
metadata before ``create_all`` runs.
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.core.logging import get_logger
from app.database.base import Base
from app.database.session import engine

logger = get_logger(__name__)

# Columns added after the first release. SQLite's create_all does not alter
# existing tables, so we add any missing ones here (lightweight migration).
_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "datasets": {
        "approval_status": "VARCHAR(16) DEFAULT 'not_required'",
        "approval_note": "TEXT",
        "reviewed_by": "INTEGER",
        "reviewed_at": "DATETIME",
        "story": "TEXT",
    },
    "issue_fixes": {
        "identifier_column": "VARCHAR(255)",
    },
}


def _apply_additive_migrations() -> None:
    """Add any missing columns to existing tables without dropping data."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _ADDITIVE_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    logger.info("Migrated: added %s.%s", table, name)


def init_db() -> None:
    """Create all database tables (and apply additive migrations)."""
    import app.models  # noqa: F401  (registers models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    _apply_additive_migrations()
    logger.info("Database initialized (%d tables).", len(Base.metadata.tables))


if __name__ == "__main__":
    init_db()
