# Changelog

## 0.1.0 - unreleased
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
