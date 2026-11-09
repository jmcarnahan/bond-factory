import types
from datetime import UTC, datetime, timedelta

from conftest import JobRecord
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from bond_jobs import claim_next, enqueue, finish, reclaim_stale
from bond_jobs.constants import backoff
from bond_jobs.engine import postgres_pick

NOW = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


def add(session_factory, job_type="t", **kw):
    with session_factory() as s:
        row = enqueue(s, JobRecord, job_type, kw.pop("payload", {}), now=kw.pop("now", NOW), **kw)
        s.commit()
        return row


def state(engine, table, job_id):
    with engine.connect() as c:
        return c.execute(select(table).where(table.c.id == job_id)).first()


def test_enqueue_key_dedupes(session_factory):
    assert add(session_factory, key="k1") is not None
    assert add(session_factory, key="k1") is None
    assert add(session_factory, key="k2") is not None


def test_enqueue_tenant_and_id(session_factory, engine, table):
    row = add(session_factory, job_id="fixed", company_id="c1", payload={"a": 1})
    got = state(engine, table, "fixed")
    assert row.id == "fixed" and got.company_id == "c1" and got.payload == {"a": 1}
    assert got.status == "pending" and got.max_attempts == 5


def test_claim_respects_run_at_and_order(session_factory, engine, table):
    late = add(session_factory, "late", run_at=NOW + timedelta(hours=1))
    second = add(session_factory, "second", run_at=NOW - timedelta(minutes=1))
    first = add(session_factory, "first", run_at=NOW - timedelta(minutes=5))
    a = claim_next(engine, table, "w1", now=NOW, real_now=NOW)
    b = claim_next(engine, table, "w1", now=NOW, real_now=NOW)
    assert (a["id"], b["id"]) == (first.id, second.id)
    assert a["attempts"] == 1 and a["worker"] == "w1"
    assert claim_next(engine, table, "w1", now=NOW, real_now=NOW) is None
    later = claim_next(engine, table, "w1", now=NOW + timedelta(hours=2), real_now=NOW)
    assert later["id"] == late.id


def test_finish_outcomes(session_factory, engine, table):
    add(session_factory, "a", max_attempts=2)
    job = claim_next(engine, table, "w1", now=NOW, real_now=NOW)
    assert finish(engine, table, job, error=None, now=NOW) == "done"
    assert state(engine, table, job["id"]).status == "done"

    add(session_factory, "b", max_attempts=2)
    job = claim_next(engine, table, "w1", now=NOW, real_now=NOW)
    assert finish(engine, table, job, error="boom" * 1000, now=NOW) == "pending"
    row = state(engine, table, job["id"])
    assert row.status == "pending" and row.run_at == (NOW + timedelta(seconds=30)).replace(tzinfo=None)
    assert len(row.last_error) == 2000 and row.locked_by is None

    job = claim_next(engine, table, "w1", now=NOW + timedelta(minutes=5), real_now=NOW)
    assert job["attempts"] == 2
    assert finish(engine, table, job, error="again", now=NOW) == "dead"

    add(session_factory, "c")
    job = claim_next(engine, table, "w1", now=NOW, real_now=NOW)
    assert finish(engine, table, job, error="no", now=NOW, permanent=True) == "dead"


def test_only_claim_holder_finishes(session_factory, engine, table):
    add(session_factory)
    job = claim_next(engine, table, "w1", now=NOW, real_now=NOW)
    thief = {**job, "worker": "w2"}
    assert finish(engine, table, thief, error=None, now=NOW) == "lost"
    assert finish(engine, table, job, error=None, now=NOW) == "done"
    assert finish(engine, table, job, error=None, now=NOW) == "lost"


def test_reclaim_uses_real_clock_and_counts_attempt(session_factory, engine, table):
    add(session_factory, "a", max_attempts=3)
    add(session_factory, "b", max_attempts=1, now=NOW - timedelta(seconds=1))
    claim_next(engine, table, "w1", now=NOW, real_now=NOW)
    claim_next(engine, table, "w1", now=NOW, real_now=NOW)
    demo_now = NOW + timedelta(days=30)  # scheduling clock far ahead: must not matter
    assert reclaim_stale(engine, table, now=demo_now, real_now=NOW + timedelta(minutes=5)) == 0
    assert reclaim_stale(engine, table, now=demo_now, real_now=NOW + timedelta(minutes=11)) == 2
    with engine.connect() as c:
        rows = {r.job_type: r for r in c.execute(select(table)).all()}
    assert rows["b"].status == "dead" and rows["b"].last_error == "Stopped responding"
    assert rows["a"].status == "pending" and rows["a"].attempts == 1
    assert rows["a"].run_at == demo_now.replace(tzinfo=None)
    again = claim_next(engine, table, "w2", now=demo_now, real_now=NOW)
    assert again["attempts"] == 2


def test_lock_stamp_is_real_now(session_factory, engine, table):
    add(session_factory)
    real = NOW + timedelta(seconds=7)
    job = claim_next(engine, table, "w1", now=NOW + timedelta(days=9), real_now=real)
    assert state(engine, table, job["id"]).locked_at == real.replace(tzinfo=None)


def test_backoff_curve():
    assert backoff(0) == timedelta(seconds=30)
    assert backoff(1) == timedelta(seconds=30)
    assert backoff(2) == timedelta(seconds=60)
    assert backoff(3) == timedelta(seconds=120)
    assert backoff(50) == timedelta(minutes=15)


def test_enqueue_race_hits_the_unique_index(session_factory, engine, table):
    """Another process inserts the key between the pre-check and the insert: the IntegrityError branch returns None."""
    add(session_factory, key="raced")
    with session_factory() as s:
        s.execute = lambda *a, **k: types.SimpleNamespace(first=lambda: None)  # the pre-check sees nothing
        assert enqueue(s, JobRecord, "t", {}, key="raced", now=NOW) is None
        del s.execute
        s.commit()
        assert s.execute(select(table.c.id)).all() != []
    with engine.connect() as c:
        assert len(c.execute(select(table).where(table.c.idempotency_key == "raced")).all()) == 1
    assert add(session_factory, key="after") is not None  # the session machinery survived the rollback


def test_postgres_claim_uses_skip_locked(table):
    sql = str(postgres_pick(table, NOW.replace(tzinfo=None)).compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "ORDER BY background_jobs.run_at, background_jobs.id" in sql
