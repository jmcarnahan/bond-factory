from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from bond_jobs import HandlerRegistry, TenantJobsMixin


class Base(DeclarativeBase):
    pass


class JobRecord(TenantJobsMixin, Base):
    pass


class FakeClock:
    """Scheduling clock and real clock are separate, like a demo that pretends to be another day."""

    def __init__(self, now=None, real=None):
        self.current = now or datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
        self.real = real or self.current

    def now(self):
        return self.current

    def real_now(self):
        return self.real

    def advance(self, **kw):
        self.current += timedelta(**kw)
        self.real += timedelta(**kw)


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def registry():
    return HandlerRegistry(JobRecord)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def table():
    return JobRecord.__table__
