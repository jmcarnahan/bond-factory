# sdk_example

Reference FastAPI app wiring every bond Python lib, in fake mode (no network, no secrets).
Route modules under `sdk_example/routes/` are discovered by `main.create_app()`.

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
| Session routes (`demo`, `/auth/me`), break-glass | `routes/auth.py`, `break_glass.py`, `session_answer.py`, `auth_dep.py`, `models/auth.py` | bond_auth_py |
| Direct sign-in (Google, Microsoft), refresh sessions, native hand-off | `signin_wiring.py`, `directory.py`, `scope_policy.py`, `models/sessions.py`, `models/handoffs.py` | bond_signin, bond_oauth, bond_auth_py |
| Connections, role asks (`wanted`, `?set=`), fake consent page | `routes/connections.py`, `connect_helpers.py`, `fake_routes.py`, `oauth_wiring.py` | bond_oauth, bond_signin |
| Documents, share links, `/d/<token>` | `routes/storage.py`, `models/grants.py` | bond_storage |
| Job table and handler registry | `models/jobs.py`, `wiring.py` | bond_jobs |
| Tasks, reminders | `routes/tasks.py`, `tasks_wiring.py` | bond_tasks_py |
| Calendar events | `routes/calendar.py`, `calendar_wiring.py` | bond_calendar |
| Job tick (fake mode) | `routes/jobs.py` | bond_jobs |
| Migrations | `alembic/versions/0001_phase2.py`, `0002_phase3.py`, `0003_signin.py` | |

`routes/a0_wiring.py` is named so it sorts before every other route module: middleware and error handlers have
to be in place before the first request, and `main.py` imports route modules alphabetically.

## Direct sign-in

The people who sign in are invited rows in `users`; the lib refuses everyone else (`not_invited`). Sign-in asks the
provider for identity only (fake-microsoft: the full set, as a pre-consented tenant would). Roles that need mail or
calendar are asked AFTER sign-in: `GET /connections` returns `{connections, wanted}` and the app sends the person
through `GET /connections/{p}/start?set=<id>`, bound to the account they signed in with.

What an app replaces: `directory.py` (its users table), `scope_policy.py` (its roles and scopes), the settings
names. Everything else is the same wiring. Environment:

| Variable | Meaning |
| --- | --- |
| `SDK_EXAMPLE_SIGNIN_PROVIDERS` | Fake mode default `fake-google,fake-microsoft`; real mode none unless named (`google`, `microsoft`); a name starting `fake` is refused outside fake mode |
| `SDK_EXAMPLE_PUBLIC_BASE` | This API's public address; the OAuth callbacks are built on it. Default `http://localhost:8012` in fake mode, required `https` in real mode |
| `SDK_EXAMPLE_NATIVE_RETURN_BASE`, `SDK_EXAMPLE_NATIVE_SCHEMES` | Phone return link (default `<base>/app/return`) and the reverse-domain scheme fallback (default `org.example.sdkdemo`) |
| `SDK_EXAMPLE_ALLOW_FAKE_PUBLIC` | `1` allows fake mode on an https `SDK_EXAMPLE_PUBLIC_BASE` (a disposable demo host only; otherwise startup refuses it) |
| `SDK_EXAMPLE_REDIRECT_ALLOWLIST`, `SDK_EXAMPLE_CORS_ORIGINS`, `SDK_EXAMPLE_NATIVE_REDIRECTS` | Defaults (`http://localhost:8078`, `sdkdemo://connections`) apply in fake mode ONLY. Real mode must set the allowlist (startup raises when empty), and every CORS origin must be in it or the public base |
| `SDK_EXAMPLE_BREAKGLASS` | `1` turns on `POST /auth/firebase` for rows flagged `allow_password` |
| `BOND_APPLE_APP_IDS`, `BOND_ANDROID_APPS` | Universal-link files; empty answers 404. Android format: `package=FP;FP,other=FP` |
| `BOND_GOOGLE_CLIENT_ID/SECRET`, `BOND_MS_CLIENT_ID/SECRET/TENANT` | Real providers; Microsoft sign-in needs the tenant GUID |

Phone clients: the device secret is hashed as a STRING (sha256 of the secret's base64url text, lowercase hex), the
same as the Dart `SignInAttempt`. Connect-native accepts the same return addresses as sign-in (the https app link
`<base>/app/return/<provider>` or a configured scheme); `SDK_EXAMPLE_NATIVE_REDIRECTS` is a deprecated alias.

Which sign-in files an app copies:

| File | An app |
| --- | --- |
| `signin_wiring.py`, `routes/signin.py`, `session_answer.py`, `connect_helpers.py`, `origin_rule.py`, `signin_prune.py` | copies as is (rename settings) |
| `routes/connections.py`, `routes/connect_native.py` (drop it with no phone client), `routes/auth.py`, `models/sessions.py`, `models/handoffs.py`, `alembic/versions/0003_signin.py` columns and tables | copies as is |
| `directory.py`, `scope_policy.py`, `oauth_wiring.py` names | REPLACES with its own users table, roles and scopes |
| `break_glass.py` (and `allow_password`) | REPLACES, or deletes when there is no break-glass |
| `fake_routes.py` | deletes (fake mode only) |

Startup refuses: a database behind the migration head (`run make migrate`), a sign-in provider named `fake*` outside
fake mode, and fake mode on an https public base. A daily `signin_prune` job (`signin_prune.py`, scheduled from the job
tick's `before` hook) deletes spent hand-offs and dead sessions. Cookie-authenticated POST/PUT/PATCH/DELETE need an
allowed `Origin` (`origin_rule.py`); bearer requests do not. An upgraded dev database: `rm out/*.db` is the simple path.

Fake consent page (`GET /connections/fake/consent`): `sdk-consent-identity`, `sdk-consent-email`,
`sdk-consent-set-<id>`, `sdk-consent-allow`, `sdk-consent-deny`. Fake-mode only: `POST /auth/simulate-reuse`.

## Fake mode

- `POST /auth/demo {"user_id": "demo-user-1"}` signs in without a password (404 outside fake mode).
- `POST /auth/firebase {"id_token": "mock:<email>"}` runs the mock verifier. The addresses it knows live in
  `out/mock_identities.json`, written at start: `demo@example.com` and `viewer@example.com` have a users row,
  `notinvited@example.com` has none (403 `not_invited`).
- `POST /auth/firebase` is the break-glass route: 404 unless `SDK_EXAMPLE_BREAKGLASS=1`, and only for rows with `allow_password`.
- Seeded users (invited, unbound until first sign-in): `demo@example.com` (`tasks.write`, `tasks.read_all`,
  `connections.manage`), `viewer@example.com` (none), `crew@example.com` (`tasks.write`),
  `demo.microsoft@example.com` (`tasks.write`, `connections.manage`). `uninvited@example.com` has no row.
- An EMPTY database gets its tables created and is stamped at the migration head, so `make migrate` later
  is a no-op. A migrated database is left alone. One that has tables but no `alembic_version` is left alone
  too, with a warning to run `make migrate`.

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
