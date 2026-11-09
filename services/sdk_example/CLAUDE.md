# sdk_example
Role: reference FastAPI app wiring every bond Python lib. Never shipped.
State: direct sign-in, auth, storage, sync, connections, tasks, calendar and jobs wired.

## Key files
- `sdk_example/wiring.py`: auth settings, storage, jobs registry, clock, middleware (installed by `routes/a0_wiring.py`).
- `sdk_example/auth_dep.py`: `current_claims`, `current_user`, `current_user_id`, `require_capability`.
- `signin_wiring.py` mounts `bond_signin`; `directory.py` and `scope_policy.py` are what an app rewrites; `session_answer.py`, `origin_rule.py`, `signin_prune.py` copy as is; `break_glass.py` optional.
- `routes/connections.py` (web), `routes/connect_native.py` (phone), `connect_helpers.py`, `fake_routes.py` (fake mode only). README has the copy/replace table.
- `sdk_example/models/`: one file per lib; `alembic/versions/` holds the single migration chain.

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_auth.py`
- `make lint`
- `make migrate` (alembic upgrade head)
- `make serve` (uvicorn factory `create_app` on :8012; no app is built at import)

## Rules
- Workspace sources allowed here only; libs stay independent.
- No network in tests.
- 300-line soft cap per source file.
- No secrets, emails or customer data (only `*@example.com`).
- A model change needs a migration; `tests/test_schema.py` fails on any drift.
