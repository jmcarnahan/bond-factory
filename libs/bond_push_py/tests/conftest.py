import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from bond_push_py import PushDevicesMixin

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "push"


class Base(DeclarativeBase):
    pass


class PushDevice(PushDevicesMixin, Base):
    pass


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def pg_session():
    """A PostgreSQL session for tests marked ``postgres``; skipped unless BOND_TEST_POSTGRES_URL is set."""
    url = os.environ.get("BOND_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("BOND_TEST_POSTGRES_URL is not set")
    engine = create_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as s:
            yield s
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
