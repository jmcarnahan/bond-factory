# bond_service_kit
Role: FastAPI and SQLAlchemy plumbing shared by the bond services (errors, middleware, rate limit, clock, db, health, mounts).

## Key files
- bond_service_kit/errors.py: `error_body`, `ApiError`, `install_error_handlers`, `UnhandledErrorMiddleware`
- bond_service_kit/middleware.py + upload_limit.py: pure-ASGI middleware
- bond_service_kit/rate_limit.py, clock.py, db.py, health.py, mounts.py

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`
- `make lint`

## Rules
- No imports from sibling bond_* libs; no app names, env names or Config singletons.
- Error body shape is docs/contracts/error_body.md; change it only with the Dart `bond_api` parser.
- Middleware stays pure ASGI (no BaseHTTPMiddleware).
- No network in tests; SQLite in memory.
- 300-line soft cap per source file.
- No secrets, emails or customer data.
