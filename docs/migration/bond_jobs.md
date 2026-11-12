# Migrating to bond_jobs

Database job queue and worker (`libs/bond_jobs`): enqueue, claim, finish, reclaim, backoff, tick, loop, with an
injected clock. Contract fields: `JobsMixin`, `HandlerRegistry`. Legend: `docs/migration/README.md`.

## 1. What it replaces

Paths: A `backend/avalon/`, P `backend/pagatime/`.

| App | Goes away | Stays app-side |
|---|---|---|
| A | in `worker.py` (771 lines): constants :36-41, `handler`, `worker_id`, `enqueue`, `claim_next`, `backoff`, `finish`, `reclaim_stale`, `run_job`, `run_due` (:44-192), `Loop`, `start_inline`, `main` skeleton; `BackgroundJobRecord` body (`db/models.py:161`); `services/errors.py` `PermanentFailure` | scheduler (`schedule_jobs` :256, `reschedule_pending`), the 20 handlers, `_tell_office_*` (:193, :219), `tick`'s demo-clock refresh, `main` startup checks, `AVALON_WORKER_INLINE` |
| P | the same engine in `worker.py` (478 lines; real-clock stamps :55, `reclaim_stale` :134-151); `BackgroundJobRecord` body (`db/models.py:184`) | scheduler, handlers, `company_id` foreign key |
| S | nothing: S has no job queue (supervisord watch scripts) | |

## 2. The adapter (A; P the same, with `company_id`)
`worker.py` keeps its public names, so 18 `enqueue(` calls (P: 14), 30 `worker.tick(` and 23 `worker.run_due(` calls are untouched:

```python
from datetime import UTC, datetime
from bond_jobs import HandlerRegistry, PermanentFailure, enqueue as _enqueue, start_inline as _start, tick as _tick, main as _main

registry = HandlerRegistry(BackgroundJobRecord)
handler = registry.handler  # @handler("crew_day_notice") unchanged

class AppClock:  # scheduling time may be the demo clock; locks and stall checks always use the real one
    def __init__(self, at: datetime | None = None): self.at = at
    def now(self) -> datetime: return self.at or utcnow_naive()
    def real_now(self) -> datetime: return datetime.now(UTC)

def enqueue(session, job_type, payload, run_at=None, key=None, max_attempts=5, job_id=None):
    return _enqueue(session, BackgroundJobRecord, job_type, payload, run_at=run_at, key=key,
                    max_attempts=max_attempts, job_id=job_id, now=utcnow_naive())  # P adds company_id=

def _before(session, now):  # was inside tick()
    try:  # the lib wraps the whole hook in one try: guard the refresh so a failure cannot skip scheduling
        demo_clock.refresh_if_due(session)
    except Exception:
        LOGGER.warning("demo clock anchor refresh failed", exc_info=True)
    schedule_jobs(session, now)

def tick(now=None, engine=None):
    return _tick(engine or get_engine(), session_scope, registry, AppClock(now), before=_before)

registry.on_dead("crew_day_notice")(lambda job: _tell_office_not_sent(job, utcnow_naive()))  # was in run_due
registry.on_dead("esign_void")(lambda job: _tell_office_void_failed(job, utcnow_naive()))

def start_inline(): return _start(tick, name="avalon-worker")
def main(argv=None) -> int:  # keep the startup lines (schema check, demo_clock.prime, pool size), then:
    return _main(argv, step=tick)
```

The model (`db/models.py`); the table already matches. P keeps its foreign key on a `JobsMixin` subclass:

```python
from bond_jobs import JobsMixin
class BackgroundJobRecord(JobsMixin, Base): pass  # P: add company_id = Column(String, ForeignKey("companies.id"), nullable=True, index=True)
```

`services/errors.py` re-exports `PermanentFailure` from `bond_jobs`, so handlers that raise it are untouched.

## 3. Call-site changes
| Old | New | Find |
|---|---|---|
| `worker.run_due(now, engine)` (A 23) | `run_due(engine, session_factory, registry, clock=AppClock(now))`, or call `tick` | `grep -rn "worker.run_due"` |
| `worker.claim_next(engine, wid, now)` (5) | `claim_next(engine, BackgroundJobRecord, wid, now=, real_now=)` | `grep -rn claim_next` |
| `worker.finish(engine, job, error, now)` (2) | `finish(engine, BackgroundJobRecord, job, error=, now=)` | `grep -rn "worker.finish"` |
| `worker.reclaim_stale(engine, now)` (2) | `reclaim_stale(engine, BackgroundJobRecord, now=, real_now=)` | `grep -rn reclaim_stale` |
| `Loop(interval)` | `Loop(interval, step)` | |
| a query on status `failed` | the set is `pending`, `running`, `done`, `dead` | `grep -rn '"failed"'` |

## 4. Data
No revision. A's table has the same 13 columns and the `ix_background_jobs_claim` index; P's adds the `company_id` column and
foreign key you declare yourself. The app tests assert it:

```python
from bond_service_kit import schema_contract
schema_contract(Base.metadata, tables=["background_jobs"]).assert_matches(engine)
```

Env and pool settings stay in the app. `POLL_SECONDS`, `STALE_AFTER`, `BACKOFF_BASE`, `BACKOFF_MAX` and `DEFAULT_MAX_ATTEMPTS` are importable.

## 5. Acceptance
- The app's worker tests, then `ruff check`. A worker run with `--once` prints one line per job on a seeded database.
- A frozen demo clock must not mark a running job stale (`reclaim_stale` returns 0 a day ahead).

## 6. Known gaps
- Not lifted: demo-clock anchors, `schedule_jobs`, all handlers, push-dead bookkeeping, startup safety checks, pool setup.
- A failing `before` hook is logged and the due jobs still run; A's `tick` raised before running them.
- Dead jobs found by `reclaim_stale` are logged only: `on_dead` hooks run when a run goes dead, as A's did.
- Datetimes are normalised to naive UTC. `backoff()` caps its exponent (the seed overflowed near 50 attempts).
- The Postgres claim path is tested as SQL text only; run `tick` once against a staging database before release.

## 7. For the TODO notices
- The notice sweep runs well as the `before` hook: `tick(..., before=sweep, before_every=60)` runs it at most once a
  minute per process, then the due jobs run. The hook gets `(session, now)` with a naive UTC `now`, and `tick`
  commits after it. A raising hook is logged and the jobs still run. Example and a plain-script variant: `bond_tasks_py.md` section 5.
- `cancel(engine, idempotency_key=..., job_table=...)` deletes pending jobs by key. `prune(engine, older_than=...,
  statuses=..., job_table=..., limit=...)` deletes old done and dead jobs. The sweep needs neither.
- `run_due` takes the clock: `now()` once per pass and `real_now()` at every claim, so a long pass does not strand a job.
