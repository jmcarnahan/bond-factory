from datetime import UTC, datetime, timedelta, timezone

from conftest import FakeClock, JobRecord
from sqlalchemy import func, select

from bond_jobs import cancel, claim_next, enqueue, prune, tick

NOW = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


def add(session_factory, job_type="t", **kw):
    with session_factory() as s:
        row = enqueue(s, JobRecord, job_type, {}, now=NOW, **kw)
        s.commit()
        return row.id


def put(session_factory, status, updated_at, key=None):
    with session_factory() as s:
        s.add(JobRecord(job_type="t", payload={}, run_at=NOW.replace(tzinfo=None), status=status, attempts=1,
                        max_attempts=5, idempotency_key=key, created_at=updated_at, updated_at=updated_at))
        s.commit()


def statuses(engine, table):
    with engine.connect() as c:
        return sorted(r.status for r in c.execute(select(table)).all())


def test_cancel_deletes_pending_with_key_only(engine, session_factory, table):
    add(session_factory, key="a")
    add(session_factory, key="b")
    assert cancel(engine, idempotency_key="a", job_table=JobRecord) == 1
    assert cancel(engine, idempotency_key="a", job_table=table) == 0
    with engine.connect() as c:
        assert [r.idempotency_key for r in c.execute(select(table)).all()] == ["b"]


def test_cancel_leaves_a_running_job_alone(engine, session_factory, table):
    add(session_factory, key="a")
    claimed = claim_next(engine, table, "w1", now=NOW, real_now=NOW)
    assert claimed["key"] == "a"
    assert cancel(engine, idempotency_key="a", job_table=table) == 0
    assert statuses(engine, table) == ["running"]


def test_prune_removes_only_old_finished_rows(engine, session_factory, table):
    old, recent = datetime(2029, 12, 1), datetime(2029, 12, 31, 23)
    for status in ("done", "dead", "pending", "running"):
        put(session_factory, status, old)
    put(session_factory, "done", recent)
    assert prune(engine, older_than=datetime(2029, 12, 15), job_table=table) == 2
    assert statuses(engine, table) == ["done", "pending", "running"]


def test_prune_never_touches_pending_or_running_even_when_asked(engine, session_factory, table):
    old = datetime(2029, 12, 1)
    for status in ("done", "dead", "pending", "running"):
        put(session_factory, status, old)
    assert prune(engine, older_than=NOW, statuses=("pending", "running", "dead"), job_table=table) == 1
    assert statuses(engine, table) == ["done", "pending", "running"]


def test_prune_statuses_and_limit_and_aware_cutoff(engine, session_factory, table):
    old = datetime(2029, 12, 1)
    for _ in range(5):
        put(session_factory, "done", old)
    put(session_factory, "dead", old)
    assert prune(engine, older_than=NOW, statuses=("dead",), job_table=table) == 1  # aware cutoff is fine
    assert prune(engine, older_than=NOW, limit=3, job_table=table) == 3
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(table)).scalar() == 2


def test_tick_before_runs_every_tick_by_default(engine, session_factory, registry, clock):
    calls = []
    for _ in range(3):
        tick(engine, session_factory, registry, clock, before=lambda s, now: calls.append(now))
        clock.advance(seconds=1)
    assert len(calls) == 3


def test_tick_before_every_throttles_by_the_wall_clock(engine, session_factory, registry):
    clock = FakeClock()
    calls = []

    def hook(session, now):
        calls.append(now)

    def go():
        tick(engine, session_factory, registry, clock, before=hook, before_every=60)

    go()
    assert len(calls) == 1  # the first tick always runs it
    clock.real += timedelta(seconds=59)
    go()
    assert len(calls) == 1
    clock.real += timedelta(seconds=1)
    go()
    assert len(calls) == 2
    clock.current += timedelta(hours=5)  # the scheduling clock alone never releases the throttle
    go()
    assert len(calls) == 2


def test_prune_reads_an_aware_cutoff_as_utc(engine, session_factory, table):
    def fill():
        with engine.begin() as c:
            c.execute(table.delete())
        for hour in (6, 9, 14):  # naive UTC update times on 2030-01-01
            put(session_factory, "done", datetime(2030, 1, 1, hour))

    def left():
        with engine.connect() as c:
            return sorted(r.updated_at.hour for r in c.execute(select(table)).all())

    fill()  # 12:00 at UTC+5 is 07:00 UTC: only the 06:00 row is older (as wall clock 12:00 the 09:00 row would go)
    assert prune(engine, older_than=datetime(2030, 1, 1, 12, tzinfo=timezone(timedelta(hours=5))),
                 job_table=table) == 1
    assert left() == [9, 14]
    fill()  # 12:00 at UTC-5 is 17:00 UTC: all three are older (as wall clock 12:00 the 14:00 row would stay)
    assert prune(engine, older_than=datetime(2030, 1, 1, 12, tzinfo=timezone(timedelta(hours=-5))),
                 job_table=table) == 3
    assert left() == []


def test_failing_before_hook_runs_again_on_the_next_tick(engine, session_factory, registry):
    clock = FakeClock()
    calls = []

    def hook(session, now):
        calls.append(now)
        if len(calls) == 1:
            raise RuntimeError("transient")

    for _ in range(3):
        tick(engine, session_factory, registry, clock, before=hook, before_every=60)
    assert len(calls) == 2  # retried at once after the failure, then throttled after the success


def test_prune_deletes_in_chunks_of_at_most_500_ids(engine, session_factory, table):
    from sqlalchemy import event

    old = datetime(2029, 12, 1)
    with session_factory() as s:
        for _ in range(1200):
            s.add(JobRecord(job_type="t", payload={}, run_at=old, status="done", attempts=1, max_attempts=5,
                            created_at=old, updated_at=old))
        s.commit()
    sizes = []

    @event.listens_for(engine, "before_cursor_execute")
    def spy(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("DELETE"):
            sizes.append(len(parameters))

    assert prune(engine, older_than=NOW, job_table=table) == 1200
    assert sizes and max(sizes) <= 500 + 2  # ids plus the status filter values
    assert len(sizes) >= 3
