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
| Session routes, break-glass | `routes/auth.py`, `break_glass.py`, `session_answer.py`, `auth_dep.py`, `models/auth.py` | bond_auth_py |
| Direct sign-in, refresh sessions, native hand-off | `signin_wiring.py`, `directory.py` (optional `apply_profile` hook), `scope_policy.py`, `models/sessions.py`, `models/handoffs.py` | bond_signin, bond_oauth |
| Connections, role asks, fake consent page | `routes/connections.py`, `connect_helpers.py`, `fake_routes.py`, `oauth_wiring.py` | bond_oauth, bond_signin |
| Documents, share links | `routes/storage.py`, `models/grants.py` | bond_storage |
| Job table, registry, fake-mode tick | `models/jobs.py`, `wiring.py`, `routes/jobs.py` | bond_jobs |
| Tasks, day view, settings, links | `routes/tasks.py`, `routes/task_*.py`, `task_support.py`, `tasks_wiring.py`, `contacts.py` | bond_tasks_py |
| Inbox, push devices, capture, sweep | `routes/notices.py`, `routes/push.py`, `routes/task_capture.py`, `todo_wiring.py`, `sweep_wiring.py` | bond_notify_py, bond_push_py, bond_capture_py |
| Sync host (notes, tasks, notices, push_devices) | `routes/sync.py`, `sync_todo.py` | bond_sync_py |
| Calendar events | `routes/calendar.py`, `calendar_wiring.py` | bond_calendar |
| Migrations | `alembic/versions/0001` to `0005_todo_tables.py` | |

`routes/a0_wiring.py` sorts before every other route module (middleware and error handlers must be in place first).
`routes/task_*.py` sort before `routes/tasks.py` on purpose: `/tasks/today` and the like must register before
`/tasks/{task_id}`.

## TODO checklist routes

Task reads take `time_zone` (else the stored setting, else `SDK_EXAMPLE_TZ`); `overdue` is open and `due_at < now`.

| Route | Answer |
| --- | --- |
| `GET/POST /tasks`, `GET/PUT/DELETE /tasks/{id}`, `POST /tasks/{id}/complete\|reopen\|cancel` | `TaskItem` (priority, due_at, time_zone on writes) |
| `GET /tasks/today`, `GET /tasks/summary` | `{overdue, today, undated, done_today, counts}`; badge counts |
| `GET/PUT /tasks/settings` | `{time_zone, start_of_day, end_of_day, lead_minutes, warnings}` |
| `POST /tasks/parse`, `GET /tasks/links/search` | candidates (creates nothing; 429 `capture_denied`); contact search |
| `GET /notices`, `POST /notices/{id}/read\|dismiss\|act`, `POST /notices/read-all` | `{items, unread_count, next_cursor}`; `act` takes `{action}` and answers `{notice, task}`; unlike read and dismiss (session only) it needs `tasks.write`, even for snooze, because done and cancel change the task |
| `POST /push/devices`, `DELETE /push/devices/{device_id}` | 201 `{device_id}`; 204 |
| `POST /capture/events`, `GET /capture/events` | the demo's stand-in for accepting an event candidate (in memory) |

Fake mode only: `POST /jobs/tick {now}` runs the sweep then the due jobs; `GET /fake/push/sent` shows what the mock
Apple sender got; `PUT /fake/capture {down}` makes the pretend model unavailable (parse degrades);
`PUT /fake/capture/limit {limit}` tightens the parse rate limit; `GET|PUT /fake/clock {now: iso Z | null}` pins
the app clock until set to null (a tick with `now` then returns to the pin; with no pin it RELEASES the clock to real time afterwards). The model replays `fixtures/capture/model_output.json`.

Running the sweep for real (both call `sweep_wiring.run_sweep`; the ledger makes two runners safe together):
1. In a worker loop: `bond_jobs.tick(..., before=sweep_wiring.before_hook(app, schedule_prune), before_every=30)`.
2. With no jobs table: `python scripts/sweep_interval.py --every 60` (`--once --now <iso>` for one pass; it also prunes).

Push goes out only with `SDK_EXAMPLE_APNS_KEY_FILE`, `_KEY_ID` and `_TEAM_ID` set (real mode); without them the
inbox still fills. SQLite engines are prepared with `sqlite_savepoint_setup` in `db.py`; the sweep refuses otherwise.

## Direct sign-in

Invited rows in `users` are the only people who sign in (`not_invited` otherwise). Sign-in asks the provider for
identity only; roles needing mail or calendar are asked after sign-in: `GET /connections` returns `{connections,
wanted}` and the app sends the person through `GET /connections/{p}/start?set=<id>`. An app replaces `directory.py`,
`scope_policy.py` and the settings names; the rest copies as is. Environment:

| Variable | Meaning |
| --- | --- |
| `SDK_EXAMPLE_SIGNIN_PROVIDERS` | Fake mode `fake-google,fake-microsoft`; real mode none unless named (`google`, `microsoft`); `fake*` is refused outside fake mode |
| `SDK_EXAMPLE_PUBLIC_BASE` | This API's public address (OAuth callbacks). Default `http://localhost:8012` in fake mode, `https` required in real mode |
| `SDK_EXAMPLE_NATIVE_RETURN_BASE`, `_NATIVE_SCHEMES`, `_NATIVE_REDIRECTS` | Phone return link, reverse-domain scheme fallback, and the deprecated exact-address alias (fake-mode defaults only) |
| `SDK_EXAMPLE_SIGNIN_PREFIX`, `_PROBE`, `_CONNECTIONS` | Library route prefix (`/auth`); daily provider probe (off); `0` mounts sign-in only |
| `SDK_EXAMPLE_REDIRECT_ALLOWLIST`, `_CORS_ORIGINS` | Defaults apply in fake mode only. Real mode must set the allowlist, and every CORS origin must be in it or the public base |
| `SDK_EXAMPLE_BREAKGLASS`, `_ALLOW_FAKE_PUBLIC` | `1` turns on `POST /auth/firebase` for `allow_password` rows; `1` allows fake mode on an https base (disposable hosts) |
| `BOND_APPLE_APP_IDS`, `BOND_ANDROID_APPS`, `BOND_GOOGLE_*`, `BOND_MS_*` | Universal-link files (empty answers 404); real provider credentials |

Files an app copies as is: `signin_wiring.py`, `providers_wiring.py`, `routes/signin.py`, `session_answer.py`,
`origin_rule.py`, `signin_prune.py`, `routes/auth.py`, the `sessions` and `handoffs` models, and the connections files
(delete those, and set `SDK_EXAMPLE_CONNECTIONS=0`, in an identity-only app). `break_glass.py` is replaced or deleted;
`fake_routes.py` and `routes/fake_todo.py` are deleted. Startup refuses a database behind the migration head, a `fake*`
provider outside fake mode, and fake mode on an https base. Cookie-authenticated mutations need an allowed `Origin`.
Phone clients hash the device secret as a string (sha256 of its base64url text, lowercase hex).

## Installed builds and cutover

- `POST /auth/refresh {id_token}` still works for installed clients through `legacy_refresh` (404 unless
  `SDK_EXAMPLE_BREAKGLASS=1`); new clients refresh with the cookie or `{refresh_token}`. `GET /connections` answers
  `{connections, wanted}`. Break-glass is the only password path.
- `client_ip` (`wiring.py`) takes the LAST `X-Forwarded-For` hop, right behind one proxy; behind two, edit it.
- Sessions have no absolute cap and a 90-day idle window; reuse detection, admin revoke-all and deactivation also end
  them. The daily `signin_prune` job (run the tick or a worker loop) deletes spent hand-offs and dead sessions.
- Cookies are `SameSite=Lax`: the web app and the API must share a registrable domain.

## Fake mode

- `POST /auth/demo {"user_id": "demo-user-1"}` signs in without a password (404 outside fake mode).
- `POST /auth/firebase {"id_token": "mock:<email>"}` runs the mock verifier (addresses in `out/mock_identities.json`).
- Seeded users: `demo@example.com` (`tasks.write`, `tasks.read_all`, `connections.manage`), `viewer@example.com`
  (none), `crew@example.com` (`tasks.write`), `demo.microsoft@example.com` (`tasks.write`, `connections.manage`).
- An EMPTY database gets its tables and is stamped at the head. A database with tables but no `alembic_version` is left
  alone with a warning; an upgraded dev database: `rm out/*.db` is the simple path.

## Protecting a route

```python
def my_route(user_id: Annotated[str, Depends(require_capability("tasks.write"))]): ...
```

The token is read from the bearer header, then the `sdk_example_access_token` cookie; the active flag, capabilities
and revocation mark are read from `users` on every request. Default to real mode in an app: fail fast on a missing
secret, as `Settings.from_env()` does, and never ship the fake defaults.
