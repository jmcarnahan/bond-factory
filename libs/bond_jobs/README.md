# bond_jobs

A small database-backed job queue: one table, atomic claims, retry with backoff, stall recovery, and a poll
loop that runs inline in the API process or as its own worker. Depends only on SQLAlchemy 2.0. Tested on
SQLite; the Postgres claim uses `FOR UPDATE SKIP LOCKED` (its SQL text is asserted in tests, and tests marked
`postgres` run it with two real processes when `BOND_TEST_POSTGRES_URL` is set).

## Attach the table

```python
from sqlalchemy.orm import DeclarativeBase
from bond_jobs import JobsMixin, TenantJobsMixin  # Tenant adds a nullable company_id (add your own FK)

class Base(DeclarativeBase): ...
class JobRecord(JobsMixin, Base): ...
```

## The table (contract)

`background_jobs` (pinned by `tests/test_schema.py`): `id` String PK (uuid), `job_type` String, `payload` JSON
(default `{}`), `run_at` DateTime (default now), `status` String (`pending|running|done|dead`, default
`pending`), `attempts` Integer (0), `max_attempts` Integer (5), `locked_at` DateTime null, `locked_by` String
null, `last_error` Text null (cut to 2000 chars), `idempotency_key` String unique null, `created_at`,
`updated_at`. Index `ix_background_jobs_claim` on `(status, run_at)`. `TenantJobsMixin` adds nullable
`company_id` String (no foreign key). Create it with your migrations or `Base.metadata.create_all`.

Constants (`bond_jobs`): `POLL_SECONDS=2.0`, `STALE_AFTER=10 min`, `BACKOFF_BASE=30 s`, `BACKOFF_MAX=15 min`,
`DEFAULT_MAX_ATTEMPTS=5`; `backoff(n) = min(30 s * 2**(n-1), 15 min)`.

## Handlers and enqueue

```python
from bond_jobs import HandlerRegistry, PermanentFailure, enqueue

registry = HandlerRegistry(JobRecord)

@registry.handler("send_reminder")
def send_reminder(session, payload, now) -> dict:      # now: naive UTC
    if payload.get("bad_key"):
        raise PermanentFailure("rejected")             # dead at once, no retry
    return {"summary": "sent"}                         # also: skipped, reason, created

@registry.on_dead("send_reminder")
def dead(job): ...                                     # job dict plus "error"; hook errors are swallowed

enqueue(session, JobRecord, "send_reminder", {"id": 1}, key="reminder:1", now=clock.now())  # None if key exists
```

`enqueue` never commits; the caller's transaction does. Retry delay is 30 s doubling to 15 min; five attempts
by default; a job `running` for 10 real minutes is put back (the stalled try counts as an attempt).

## Run it

```python
from bond_jobs import SystemClock, tick, start_inline, main

def step():
    return tick(engine, session_factory, registry, SystemClock(), before=schedule)  # before(session, now)

thread, loop = start_inline(step)                       # inline: daemon thread in the API process
# worker process: raise SystemExit(main(step=step))      # `--once` runs a single pass
```

`main --once` runs one pass and prints one line per job (`<status> <job_type>  <summary>`); it is the only
`print()` in the library.

`before` is the app's scheduler (enqueue what is due, using idempotency keys). `before_every=60` runs it at most
once per 60 wall-clock seconds per process (the first tick always runs it); the default runs it every tick. A failing hook is logged and the
due jobs still run. `session_factory` is a SQLAlchemy `sessionmaker`; each job runs in its own session and the
engine commits it after the handler returns.

## The two clocks

A `Clock` has `now()` and `real_now()`, both aware UTC. `now()` is the scheduling clock: due checks and retry
times. It may be offset (a demo pretending to be another day). `real_now()` is the wall clock: `locked_at` and
stall checks use it only, so an offset scheduling clock never makes a healthy job look stale. Stored times are
naive UTC; every function accepts aware or naive input.

## Lower-level calls

`claim_next`, `finish` (returns `done|dead|pending|lost`; only the claim holder can finish), `reclaim_stale`,
`run_job` take the engine and the job table (or model) explicitly. `run_due(engine, session_factory,
registry, *, clock, wid=None, limit=200)` takes the `Clock`: `now()` once per pass, `real_now()` at every claim
(so `locked_at` is the claim time, never the pass start).

## Cancel and prune

```python
from bond_jobs import cancel, prune

cancel(engine, idempotency_key="reminder:1", job_table=JobRecord)   # deletes pending jobs only; returns count (job_table is required)
prune(engine, older_than=cutoff, job_table=JobRecord)               # done/dead rows updated before cutoff
```

`cancel` leaves a running job alone. `prune` takes `statuses=("done", "dead")` and `limit=10000`; pending and
running rows are never deleted. Both are plain deletes on the engine and commit on their own.
