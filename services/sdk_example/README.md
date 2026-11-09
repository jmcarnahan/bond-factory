# sdk_example

Reference FastAPI app wiring every bond Python lib, in fake mode (no network, no secrets).
Route modules under `sdk_example/routes/` are discovered by `main.create_app()`; tasks and jobs routes land in phase 3.

```
make -C services/sdk_example test
make -C services/sdk_example migrate   # alembic upgrade head on out/sdk_example.db
make -C services/sdk_example serve     # uvicorn on :8012, built through the create_app factory
```

Settings come from `SDK_EXAMPLE_*` variables (see `sdk_example/settings.py`). With none set the app starts in
fake mode and logs one warning. Real mode needs `SDK_EXAMPLE_AUTH_SECRET`, and a `*` CORS origin is refused.

## What is wired

| Piece | Where | Lib |
| --- | --- | --- |
| Error body, security headers, upload cap | `wiring.py` (installed by `routes/a0_wiring.py`) | bond_service_kit |
| Sign-in, session, `/auth/*` | `routes/auth.py`, `auth_dep.py`, `models/auth.py` | bond_auth_py |
| Documents, share links, `/d/<token>` | `routes/storage.py`, `models/grants.py` | bond_storage |
| Job table and handler registry | `models/jobs.py`, `wiring.py` | bond_jobs |

`routes/a0_wiring.py` is named so it sorts before every other route module: middleware and error handlers have
to be in place before the first request, and `main.py` imports route modules alphabetically.

## Fake mode

- `POST /auth/demo {"user_id": "demo-user-1"}` signs in without a password (404 outside fake mode).
- `POST /auth/firebase {"id_token": "mock:<email>"}` runs the mock verifier. The addresses it knows live in
  `out/mock_identities.json`, written at start: `demo@example.com` and `viewer@example.com` have a users row,
  `notinvited@example.com` has none (403 `not_invited`).
- Seeded users: `demo-user-1` (capabilities `tasks.write`, `connections.manage`) and `demo-user-2` (none).
- An unmigrated database gets its tables created and is stamped at the migration head, so `make migrate` later
  is a no-op. A migrated database is left alone.

## Protecting a route

```python
from typing import Annotated
from fastapi import Depends
from sdk_example.auth_dep import current_user_id, require_capability

def my_route(user_id: Annotated[str, Depends(require_capability("tasks.write"))]): ...
```

The token is read from the bearer header first, then the `sdk_example_access_token` cookie. The active flag,
the capabilities and the revocation mark are read from the users table on every request.

## Copying this into an app

Default to real mode. Fake mode (mock identities, demo auth, generated keys in `out/`) exists so the example
and its tests run with no setup. An app should fail fast on a missing secret, as `Settings.from_env()` does
for real mode, and never ship the fake defaults.
