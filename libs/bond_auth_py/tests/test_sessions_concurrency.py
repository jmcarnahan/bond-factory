"""Two threads rotating the same token on a SQLite FILE database: the atomic claim has exactly one winner."""

import threading

import pytest
from sessions_support import T0, AuthSession, Base, Revocation, loader, settings_with
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from bond_auth_py import ReuseDetected, SessionStore


@pytest.fixture
def file_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sessions.db'}", connect_args={"timeout": 30})
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def race(factory, store, token):
    barrier = threading.Barrier(2)
    results = [None, None]

    def work(i):
        with factory() as session:
            barrier.wait(timeout=10)
            try:
                results[i] = store.rotate(session, refresh_token=token, rotation_id=None, loader=loader,
                                          revocation=Revocation(), now=T0 + 100)
                session.commit()
            except Exception as exc:  # noqa: BLE001 - the outcome is the assertion
                session.rollback()
                results[i] = exc

    threads = [threading.Thread(target=work, args=(i,)) for i in range(2)]
    [t.start() for t in threads]
    [t.join(timeout=60) for t in threads]
    assert not any(t.is_alive() for t in threads)
    return results


def snapshot(factory):
    with factory() as session:
        return list(session.execute(select(AuthSession).order_by(AuthSession.created_at)).scalars())


@pytest.mark.parametrize("run", [1, 2, 3])
def test_strict_grace_exactly_one_thread_wins(file_factory, run):
    store = SessionStore(AuthSession, settings_with(refresh_reuse_grace_seconds=0))
    with file_factory() as session:
        first = store.issue(session, user_id="u1", auth_time=T0, provider="google", spec=loader("u1"), now=T0)
        session.commit()
    results = race(file_factory, store, first.refresh_token)
    wins = [r for r in results if not isinstance(r, Exception)]
    assert len(wins) == 1 and sum(isinstance(r, ReuseDetected) for r in results) == 1
    rows = snapshot(file_factory)
    assert sum(1 for r in rows if r.rotated_at is not None) == 1  # one claim of the parent
    assert all(r.revoked_at is not None for r in rows)  # the loser's reuse committed the revocation


@pytest.mark.parametrize("run", [1, 2, 3])
def test_default_grace_one_claim_and_the_loser_gets_a_sibling(file_factory, run):
    store = SessionStore(AuthSession, settings_with())
    with file_factory() as session:
        first = store.issue(session, user_id="u1", auth_time=T0, provider="google", spec=loader("u1"), now=T0)
        session.commit()
    results = race(file_factory, store, first.refresh_token)
    assert all(not isinstance(r, Exception) for r in results)
    assert results[0].refresh_token != results[1].refresh_token
    rows = snapshot(file_factory)
    assert len(rows) == 3 and sum(1 for r in rows if r.rotated_at is not None) == 1
    assert all(r.revoked_at is None for r in rows)
