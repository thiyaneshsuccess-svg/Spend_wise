"""Test fixtures.

Everything runs against an in-memory SQLite database, so the whole suite is
hermetic and fast. The API client shares one session with the assertions,
which lets a test read the database directly after an HTTP call.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.app import create_app
from app.db.base import Base
from app.db.models import Account, User
from app.db.session import get_session, make_engine


@pytest.fixture()
def engine() -> Iterator[Engine]:
    test_engine = make_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture()
def session(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db_session:
        yield db_session


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def account(session: Session) -> Account:
    user = User(email="tester@example.com", display_name="Tester")
    session.add(user)
    session.flush()
    row = Account(user_id=user.id, name="Test Bank", kind="bank")
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
