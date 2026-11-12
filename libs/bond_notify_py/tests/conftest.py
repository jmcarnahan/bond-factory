import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from bond_notify_py import NoticesMixin

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "notify"


class Base(DeclarativeBase):
    pass


class Notice(NoticesMixin, Base):
    pass


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def pg_engine():
    """A PostgreSQL engine for tests marked ``postgres``; skipped unless BOND_TEST_POSTGRES_URL is set."""
    url = os.environ.get("BOND_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("BOND_TEST_POSTGRES_URL is not set")
    engine = create_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def session(request):
    """The same service tests on in-memory SQLite and, when BOND_TEST_POSTGRES_URL is set, on PostgreSQL."""
    if request.param == "postgres":
        engine = request.getfixturevalue("pg_engine")
    else:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
