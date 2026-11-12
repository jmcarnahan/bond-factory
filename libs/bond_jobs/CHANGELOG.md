# Changelog

## 0.1.0 - unreleased
- `interval.py`: `Every(seconds, fn, name="", jitter=0.0, run_first=True)`, `run_schedule(entries, *, stop, install_signals,
  on_result, guard, clock, wait)`, `run_every(fn, seconds, **kw)`, `run_cli(argv, entries, *, guard, on_result, stop, install_signals)` (`--once`, `--watch`,
  `--interval N`; `--once` honours `guard` and `on_result`), `MIN_SECONDS`. Timer-only runner: no jobs table, no SQLAlchemy. Fixed rate, one thread, earliest due first.
- `interval.py` rejects non-finite `seconds`, `jitter` and `--interval`, caps each wait at `threading.TIMEOUT_MAX`, restores signal
  handlers at the first signal, and skips restoring a `None` handler.
- Job queue: `JobsMixin`, `TenantJobsMixin`, `HandlerRegistry` (handlers, dead-job hooks), `enqueue`,
  `claim_next`, `finish`, `reclaim_stale`, `run_job`, `run_due`, `tick`, `Loop`, `start_inline`, `main`.
- Two-clock contract: scheduling `now()`, wall-clock `real_now()` for lock stamps and stall checks.
- `run_due(engine, session_factory, registry, *, clock, wid=None, limit=200, job_table=None)` takes the `Clock`:
  `now()` is read once per pass, `real_now()` at every claim, so `locked_at` is the claim time and a job claimed
  late in a long pass is never reclaimed as stale. `tick` passes its clock through.
- `tick(..., before_every=seconds)` throttles the `before` hook per process by the wall clock; `None` keeps
  the every-tick behaviour.
- `cancel(engine, *, idempotency_key, job_table)` deletes pending jobs by key; `prune(engine, *, older_than,
  statuses, job_table, limit)` deletes old done/dead jobs.
- Postgres-marked tests: two-process claim, stale reclaim, concurrent enqueue, cancel and prune.
- `backoff` caps its exponent (the app versions overflowed for very large attempt counts).
