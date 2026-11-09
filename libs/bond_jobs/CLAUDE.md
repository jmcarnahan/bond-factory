# bond_jobs
Role: database-backed job queue and worker loop (SQLAlchemy 2.0 only). Contract: the README (table and constants); tests/test_schema.py pins the table.

## Key files
- `models.py` mixins; `engine.py` registry + enqueue/claim/finish/reclaim/run/tick; `loop.py` Loop/main
- `clock.py` Clock Protocol (scheduling `now()` vs wall `real_now()`); `constants.py` tuning + `backoff`

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`
- `make lint`

## Rules
- No imports from sibling bond_* libs. No network in tests (SQLite in-memory; Postgres SQL asserted as text).
- Lock stamps and stall checks use `real_now`, never the scheduling clock.
- 300-line soft cap per source file. No secrets, emails or customer data.
