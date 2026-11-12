"""The claim and enqueue paths against a real PostgreSQL. Skipped unless BOND_TEST_POSTGRES_URL is set."""

import multiprocessing
import os
from datetime import UTC, datetime, timedelta

import pytest
from conftest import Base, JobRecord
from pg_workers import claim_and_run, enqueue_keys
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from bond_jobs import HandlerRegistry, SystemClock, cancel, claim_next, enqueue, prune, tick

pytestmark = pytest.mark.postgres
NOW = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def pg_url():
    url = os.environ.get("BOND_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("BOND_TEST_POSTGRES_URL is not set")
    return url


@pytest.fixture
def pg_engine(pg_url):
    engine = create_engine(pg_url)
    with engine.begin() as c:
        c.execute(text("drop table if exists job_runs"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as c:
        c.execute(text("create table job_runs (job_id integer not null, pid integer not null)"))
    try:
        yield engine
    finally:
        with engine.begin() as c:
            c.execute(text("drop table if exists job_runs"))
        Base.metadata.drop_all(engine)
        engine.dispose()


def run_two(url, target, args=()):
    """Run ``target(url, start, out, *args)`` in two spawned processes released together; returns both results."""
    ctx = multiprocessing.get_context("spawn")
    start, out = ctx.Event(), ctx.Queue()
    procs = [ctx.Process(target=target, args=(url, start, out, *args)) for _ in range(2)]
    for p in procs:
        p.start()
    start.set()
    results = [out.get(timeout=120) for _ in procs]
    for p in procs:
        p.join(60)
        assert p.exitcode == 0
    return results


def test_two_processes_run_every_job_exactly_once(pg_engine, pg_url):
    factory = sessionmaker(pg_engine, expire_on_commit=False)
    with factory() as s:
        for n in range(500):
            enqueue(s, JobRecord, "count", {"n": n}, now=datetime.now(UTC) - timedelta(minutes=1))
        s.commit()
    ran = run_two(pg_url, claim_and_run)
    assert sum(ran) == 500
    assert all(r > 0 for r in ran)  # both processes took part
    with pg_engine.connect() as c:
        runs = c.execute(text("select job_id from job_runs")).scalars().all()
        done = c.execute(select(func.count()).select_from(JobRecord.__table__).where(
            JobRecord.__table__.c.status == "done")).scalar()
    assert sorted(runs) == list(range(500))  # none lost, none twice
    assert done == 500


def test_a_job_left_running_past_its_lease_is_picked_up_again(pg_engine):
    factory = sessionmaker(pg_engine, expire_on_commit=False)
    with factory() as s:
        enqueue(s, JobRecord, "count", {"n": 7}, now=datetime.now(UTC) - timedelta(hours=1), key="k")
        s.commit()
    stale = datetime.now(UTC) - timedelta(minutes=11)
    claimed = claim_next(pg_engine, JobRecord, "dead-worker", now=datetime.now(UTC), real_now=stale)
    assert claimed["attempts"] == 1
    registry = HandlerRegistry(JobRecord)
    seen = []

    @registry.handler("count")
    def count(session, payload, now):
        seen.append(payload["n"])
        return {}

    out = tick(pg_engine, factory, registry, SystemClock())
    assert seen == [7]
    assert [r["status"] for r in out] == ["done"]
    with pg_engine.connect() as c:
        row = c.execute(select(JobRecord.__table__)).one()
    assert row.status == "done" and row.attempts == 2


def test_a_fresh_running_job_is_not_reclaimed(pg_engine):
    factory = sessionmaker(pg_engine, expire_on_commit=False)
    with factory() as s:
        enqueue(s, JobRecord, "count", {"n": 1}, now=datetime.now(UTC) - timedelta(hours=1))
        s.commit()
    assert claim_next(pg_engine, JobRecord, "w", now=datetime.now(UTC), real_now=datetime.now(UTC)) is not None
    assert tick(pg_engine, factory, HandlerRegistry(JobRecord), SystemClock()) == []


def test_same_key_from_two_processes_yields_one_job(pg_engine, pg_url):
    keys = [f"k{i}" for i in range(40)]
    made = run_two(pg_url, enqueue_keys, (keys,))
    assert sum(made) == 40  # each key was created by exactly one of the two processes
    with pg_engine.connect() as c:
        found = c.execute(select(JobRecord.__table__.c.idempotency_key)).scalars().all()
    assert sorted(found) == sorted(keys)


def test_cancel_and_prune_on_postgres(pg_engine):
    factory = sessionmaker(pg_engine, expire_on_commit=False)
    table = JobRecord.__table__
    old = datetime(2029, 12, 1)
    with factory() as s:
        enqueue(s, JobRecord, "count", {"n": 1}, key="a", now=NOW)
        enqueue(s, JobRecord, "count", {"n": 2}, key="b", now=NOW)
        for status in ("done", "dead", "running"):
            s.add(JobRecord(job_type="count", payload={}, status=status, run_at=old, created_at=old,
                            updated_at=old, attempts=1, max_attempts=5))
        s.commit()
    assert cancel(pg_engine, idempotency_key="a", job_table=JobRecord) == 1
    assert prune(pg_engine, older_than=NOW, job_table=JobRecord) == 2
    with pg_engine.connect() as c:
        left = sorted(r.status for r in c.execute(select(table)).all())
    assert left == ["pending", "running"]
