# 2026-11-12 Interval runner in bond_jobs

Status: accepted. Dated, append-only.

## Context

`bond_jobs` has a worker loop built on its jobs table. A service with no jobs table, or one that wants a sweep every
minute and a prune every hour from one process, hand-rolled a loop with its own signal handling. The example's
`scripts/sweep_interval.py` was one such loop.

## Decisions

- **I1** `bond_jobs.interval` runs plain functions on timers: no database, no SQLAlchemy. `Every(seconds, fn, name="",
  jitter=0.0, run_first=True)` describes one entry. `run_schedule(entries, ...)` runs them on one thread, the earliest
  due first. `run_every(fn, seconds)` is the one-entry form. `run_cli(argv, entries)` is a worker entry point with
  `--once` and `--watch --interval N`.
- **I2** The rate is fixed: an entry's next due time is its previous due time plus `seconds`, so a slow run does not
  drift the schedule. A run that missed periods runs once and realigns to the next point on its grid. There is no
  burst of catch-up runs. The smallest period is 0.01 s, to catch milliseconds passed as seconds.
- **I3** An entry that raises is logged and the others carry on. `on_result(entry, result, error)` sees every run.
- **I4** `guard(entry)` is an optional callable. When it returns false the run is skipped. A cross-process lock belongs
  there; the library ships none.
- **I5** SIGINT and SIGTERM set the stop event, only on the main thread, and the previous handlers are restored on exit.
  `stop`, `clock` and `wait` can be injected, so tests need no real time.
- **I6** The runner does not configure logging. The calling script does.

## Consequences

- One worker process can host several schedules. Two copies of a worker still need the work itself to be safe to
  repeat (the task sweep is: its ledger claim is exactly once).
- `run_cli` does not parse an app's own flags (the example's `--now`), so such a script keeps its own argument parser
  and calls `run_schedule` directly.
