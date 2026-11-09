# sdk_example
Role: reference FastAPI app wiring every bond Python lib. Never shipped.
State: auth, storage, sync and connections wired; tasks and jobs routes land in phase 3.

## Key files
- `sdk_example/wiring.py`: auth settings, storage, jobs registry, clock, middleware (installed by `routes/a0_wiring.py`).
- `sdk_example/auth_dep.py`: `current_claims`, `current_user`, `current_user_id`, `require_capability`.
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
