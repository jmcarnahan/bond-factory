# sdk_example
Role: reference FastAPI app wiring every bond Python lib. Never shipped.
State: phase 1 skeleton (`/health` only); lib routes land in phases 2 and 3.

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_health.py`
- `make lint`
- `make serve` (uvicorn factory `create_app` on :8012; no app is built at import)

## Rules
- Workspace sources allowed here only; libs stay independent.
- No network in tests.
- 300-line soft cap per source file.
- No secrets, emails or customer data.
