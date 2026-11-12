# sdk_example
Role: reference FastAPI app wiring every bond Python lib. Never shipped.
State: sign-in, auth, storage, sync, connections, tasks (due instants, day view, settings), inbox, push, capture, calendar, jobs.

## Key files
- `sdk_example/wiring.py`: auth settings, storage, jobs registry, clock, middleware (installed by `routes/a0_wiring.py`).
- `sdk_example/auth_dep.py`: `current_claims`, `current_user`, `current_user_id`, `require_capability`.
- `signin_wiring.py` mounts `bond_signin`; `directory.py` and `scope_policy.py` are what an app rewrites; `providers_wiring.py` builds providers; `fake_routes.py` and `routes/fake_todo.py` are fake mode only. README has the copy/replace table.
- TODO checklist: `todo_wiring.py` (state on `app.state`, `after_task_write`), `task_support.py` (zone, item, write hook), `routes/task_*.py` (must sort before `tasks.py`), `routes/notices.py`, `routes/push.py`, `sync_todo.py`, `sweep_wiring.py`, `scripts/sweep_interval.py`, `contacts.py`, `capture_wiring.py`.
- `sdk_example/models/`: one file per concern; `alembic/versions/` holds the single migration chain.

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_auth.py`; `make lint`; `make migrate`; `make serve` (:8012)
- `python scripts/sweep_interval.py --once --now <iso>`: one sweep pass

## Rules
- Workspace sources allowed here only; libs stay independent. No network in tests.
- 300-line soft cap per source file. No secrets, emails or customer data (only `*@example.com`).
- A model change needs a migration; `tests/test_schema.py` fails on any drift.
- Every task read passes `now` and the viewer zone; every complete, cancel or delete calls `dismiss_for_source`, every write `dismiss_stale` (`todo_wiring.after_task_write`).
- Tests freeze the app clock at 2026-11-08 10:00 UTC (`conftest.py`); `/jobs/tick` pins its own time, then returns to the `PUT /fake/clock` pin or releases.
