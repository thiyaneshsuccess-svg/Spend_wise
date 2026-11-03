"""Engine/session construction.

SQLite is the default so the app runs with zero infrastructure. The same code
path works against Postgres by changing ``SPENDWISE_DATABASE_URL``; nothing in
``domain/`` or ``analytics/`` knows which database is in use.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db.base import Base


def _apply_sqlite_pragmas(engine: Engine) -> None:
    """SQLite ignores foreign keys unless asked, per connection."""

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def make_engine(url: str) -> Engine:
    kwargs: dict[str, object] = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if url in {"sqlite://", "sqlite:///:memory:"}:
            # One shared in-memory database for the whole test session.
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)  # type: ignore[arg-type]
    if url.startswith("sqlite"):
        _apply_sqlite_pragmas(engine)
    return engine


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, closed afterwards."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all(target_engine: Engine | None = None) -> None:
    """Create the schema from models.

    Used by tests only — real environments run Alembic migrations, so that the
    schema has a reviewable history rather than appearing by magic.
    """
    Base.metadata.create_all(target_engine or engine)
