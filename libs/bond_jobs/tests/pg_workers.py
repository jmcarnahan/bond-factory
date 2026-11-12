"""Functions run in spawned processes by test_postgres.py. Each process builds its own engine."""

import os
from datetime import UTC, datetime

from conftest import JobRecord
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from bond_jobs import HandlerRegistry, SystemClock, enqueue, run_due

NOW = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


def _registry():
    registry = HandlerRegistry(JobRecord)

    @registry.handler("count")
    def count(session, payload, now):
        session.execute(text("insert into job_runs (job_id, pid) values (:j, :p)"),
                        {"j": payload["n"], "p": os.getpid()})
        return {"summary": "ok"}

    return registry


def claim_and_run(url, start, out):
    engine = create_engine(url)
    factory = sessionmaker(engine, expire_on_commit=False)
    registry = _registry()
    start.wait(30)
    ran = 0
    while True:
        got = run_due(engine, factory, registry, clock=SystemClock(), limit=25)
        if not got:
            break
        ran += len(got)
    engine.dispose()
    out.put(ran)


def enqueue_keys(url, start, out, keys):
    engine = create_engine(url)
    factory = sessionmaker(engine, expire_on_commit=False)
    start.wait(30)
    made = 0
    for key in keys:
        with factory() as s:
            if enqueue(s, JobRecord, "count", {"n": 0}, key=key, now=NOW) is not None:
                made += 1
            s.commit()
    engine.dispose()
    out.put(made)
