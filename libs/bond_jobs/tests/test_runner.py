import threading
from datetime import timedelta

import pytest
from conftest import Base, FakeClock, JobRecord
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from bond_jobs import HandlerRegistry, Loop, PermanentFailure, claim_next, enqueue, run_due, tick
from bond_jobs import engine as engine_module


def add(session_factory, clock, job_type, **kw):
    with session_factory() as s:
        row = enqueue(s, JobRecord, job_type, kw.pop("payload", {}), now=clock.now(), **kw)
        s.commit()
        return row


def rows(engine, table):
    with engine.connect() as c:
        return {r.job_type: r for r in c.execute(select(table)).all()}


def test_tick_runs_handler_and_records_summary(engine, session_factory, registry, clock, table):
    seen = []

    @registry.handler("greet")
    def greet(session, payload, now):
        seen.append((payload, now.tzinfo))
        return {"summary": "hello", "created": ["x"]}

    @registry.handler("noop")
    def noop(session, payload, now):
        return {"skipped": True}

    add(session_factory, clock, "greet", payload={"who": "a"}, key="g1")
    add(session_factory, clock, "noop")
    out = tick(engine, session_factory, registry, clock)
    by_type = {r["job_type"]: r for r in out}
    assert by_type["greet"]["summary"] == "hello" and by_type["greet"]["created"] == ["x"]
    assert by_type["greet"]["key"] == "g1" and by_type["greet"]["status"] == "done"
    assert by_type["noop"]["skipped"] and by_type["noop"]["reason"] == "nothing_due"
    assert seen == [({"who": "a"}, None)]  # handlers get naive UTC
    assert rows(engine, table)["greet"].status == "done"


def test_tick_before_hook_schedules_and_survives_errors(engine, session_factory, registry, clock):
    registry.handler("sched")(lambda s, p, n: {"summary": "ran"})

    def before(session, now):
        enqueue(session, JobRecord, "sched", {}, key="s1", now=now)

    out = tick(engine, session_factory, registry, clock, before=before)
    assert [r["job_type"] for r in out] == ["sched"]
    assert tick(engine, session_factory, registry, clock, before=before) == []  # key already used

    def broken(session, now):
        raise RuntimeError("scheduler down")

    add(session_factory, clock, "sched")
    assert len(tick(engine, session_factory, registry, clock, before=broken)) == 1


def test_failure_retries_with_backoff_then_dies(engine, session_factory, registry, clock, table):
    @registry.handler("flaky")
    def flaky(session, payload, now):
        raise ValueError("nope")

    add(session_factory, clock, "flaky", max_attempts=2)
    first = run_due(engine, session_factory, registry, clock=clock)
    assert first[0]["status"] == "pending" and first[0]["error"] == "ValueError: nope"
    assert run_due(engine, session_factory, registry, clock=clock) == []
    clock.advance(minutes=2)
    second = run_due(engine, session_factory, registry, clock=clock)
    assert second[0]["status"] == "dead"
    assert rows(engine, table)["flaky"].attempts == 2


def test_permanent_failure_dies_at_once_and_fires_hook(engine, session_factory, registry, clock, table):
    dead = []

    @registry.handler("keyed")
    def keyed(session, payload, now):
        raise PermanentFailure("rejected key")

    @registry.on_dead("keyed")
    def remember(job):
        dead.append((job["id"], job["error"]))

    @registry.on_dead("keyed")
    def explode(job):
        raise RuntimeError("hook bug")  # must not stop the run

    row = add(session_factory, clock, "keyed", max_attempts=5)
    out = run_due(engine, session_factory, registry, clock=clock)
    assert out[0]["status"] == "dead"
    assert dead == [(row.id, "PermanentFailure: rejected key")]
    assert rows(engine, table)["keyed"].attempts == 1


def test_missing_handler_is_recorded(engine, session_factory, registry, clock):
    add(session_factory, clock, "ghost", max_attempts=1)
    out = run_due(engine, session_factory, registry, clock=clock)
    assert out[0]["status"] == "dead" and "No handler" in out[0]["error"]


def test_run_due_limit_and_table_required(engine, session_factory, clock):
    registry = HandlerRegistry()
    with pytest.raises(ValueError):
        run_due(engine, session_factory, registry, clock=clock)
    registry.handler("t")(lambda s, p, n: {})
    for _ in range(3):
        add(session_factory, clock, "t")
    out = run_due(engine, session_factory, registry, clock=clock,
                  limit=2, job_table=JobRecord)
    assert len(out) == 2


def test_naive_and_aware_clocks_agree(engine, session_factory, registry, clock):
    registry.handler("t")(lambda s, p, n: {})
    add(session_factory, clock, "t", run_at=clock.now() - timedelta(seconds=1))
    naive = clock.now().replace(tzinfo=None)
    assert len(run_due(engine, session_factory, registry, clock=FakeClock(naive, naive))) == 1


class StepClock:
    """The wall clock jumps forward 11 minutes every time it is read after the first read."""

    def __init__(self, start):
        self.start, self.reads = start, 0

    def now(self):
        return self.start

    def real_now(self):
        self.reads += 1
        return self.start + timedelta(minutes=11 * (self.reads - 1))


def test_locked_at_is_read_per_claim_not_per_pass(engine, session_factory, registry, table):
    clock = StepClock(FakeClock().now())
    seen = []
    registry.handler("t")(lambda s, p, n: seen.append(p["n"]) or {})
    for n in range(2):
        add(session_factory, clock, "t", payload={"n": n})
    claims = []
    real_claim = engine_module.claim_next
    engine_module.claim_next = lambda *a, **k: claims.append(k["real_now"]) or real_claim(*a, **k)
    try:
        run_due(engine, session_factory, registry, clock=clock)
    finally:
        engine_module.claim_next = real_claim
    assert claims[1] - claims[0] == timedelta(minutes=11)  # a fresh real_now for the second claim
    assert sorted(seen) == [0, 1]


def test_second_claim_stamps_the_later_time(engine, session_factory, table):
    clock = StepClock(FakeClock().now())
    for _ in range(2):
        add(session_factory, clock, "t")
    first = claim_next(engine, table, "w", now=clock.now(), real_now=clock.real_now())
    second = claim_next(engine, table, "w", now=clock.now(), real_now=clock.real_now())
    with engine.connect() as c:
        stamps = {r.id: r.locked_at for r in c.execute(select(table)).all()}
    assert stamps[second["id"]] - stamps[first["id"]] == timedelta(minutes=11)


def test_concurrent_claims_never_duplicate(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'jobs.db'}", connect_args={"check_same_thread": False, "timeout": 30})
    Base.metadata.create_all(eng)
    factory = sessionmaker(eng, expire_on_commit=False)
    table = JobRecord.__table__
    now = FakeClock().now()
    with factory() as s:
        for n in range(200):
            enqueue(s, JobRecord, "t", {"n": n}, now=now)
        s.commit()
    taken, lock = [], threading.Lock()

    def worker(i):
        while (job := claim_next(eng, table, f"w{i}", now=now, real_now=now)) is not None:
            with lock:
                taken.append(job["id"])

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert len(taken) == 200 and len(set(taken)) == 200
    eng.dispose()


def test_loop_runs_until_stopped_and_survives_errors():
    calls = []

    def step():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("bad pass")
        loop.stop.set()
        return []

    loop = Loop(0.001, step)
    loop.run()
    assert len(calls) == 2
