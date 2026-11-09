"""Shared helpers for the refresh-session tests (a plain module: pytest puts this directory on sys.path)."""

import time
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from bond_auth_py import AuthSettings, SessionsMixin, SessionSpec, SessionStore

SECRET = "test-secret-that-is-long-enough-for-hs256"
Base = declarative_base()


class AuthSession(SessionsMixin, Base):
    user_fk_target = None


T0 = float(int(time.time()))  # whole seconds: exact-boundary assertions must not hit microsecond rounding
DAY = 86400.0


class Revocation:
    """``RevocationCheck`` backed by one mutable value (naive or aware datetime, or None)."""

    def __init__(self, value=None):
        self.value = value

    def sessions_valid_after(self, user_id):
        return self.value


def at(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def loader(user_id):
    return SessionSpec(user_id, "User", ["a.b"], {"company_id": "c1"})


def settings_with(**overrides) -> AuthSettings:
    return AuthSettings(jwt_secret=SECRET, **overrides)


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.drop_all(engine)


@pytest.fixture
def db(factory):
    with factory() as session:
        yield session


@pytest.fixture
def store():
    return SessionStore(AuthSession, settings_with())


@contextmanager
def scope(factory):
    """Commit on success, ROLL BACK on exception: the example's ``db.session_scope``."""
    session = factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def rows(session, family_id=None):
    session.expire_all()
    query = select(AuthSession).order_by(AuthSession.created_at, AuthSession.id)
    if family_id is not None:
        query = query.where(AuthSession.family_id == family_id)
    return list(session.execute(query).scalars())


def issue(store, db, *, user="u1", now=T0, **kw):
    kw.setdefault("auth_time", time.time() if now is None else now)
    kw.setdefault("provider", "google")
    issued = store.issue(db, user_id=user, spec=loader(user), now=now, **kw)
    db.commit()
    return issued


def rotate(store, db, token, *, now, rid=None, revocation=None, probe=None, commit=True, **kw):
    out = store.rotate(db, refresh_token=token, rotation_id=rid, loader=kw.pop("loader", loader),
                       revocation=revocation or Revocation(), probe=probe, now=now)
    if commit:
        db.commit()
    return out
