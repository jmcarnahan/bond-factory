# Migrating to bond_sync_py

Contracts: `docs/contracts/sync_upload.md`. Fixtures: `fixtures/sync/`. Both apps keep their routes, tables and
handlers; only the generic core moves into `libs/bond_sync_py`. Legend: `docs/migration/README.md`.

## 1. What it replaces

What the lib holds:

| Module | Holds |
|---|---|
| `envelope` | `UploadOp`, `UploadRequest` (extra=forbid, <= 100 ops, unique seq), `OpResult`, `UploadResponse`, `server_now_iso` |
| `verdicts` | codes, `Rejected`, `Skipped`, `Resolved`, `DbUnavailable`, `is_database_down`, `ok/rejected/skipped` |
| `coerce` | client bools, JSON text, numbers, ISO datetimes; NUL byte check |
| `routes` | `Route`, `Ctx`, `Host`, `route_for` |
| `dispatcher` | `apply`, `upload` (one transaction per op, seq order) |
| `replay` | `LoggedBugs`, `written_by` |
| `tokens` | `SyncTokenSettings` (+ `from_env`), `mint_sync_token`, `jwks`, `load_private_key`, `is_configured`, `key_reason` |
| `publication`, `source_sql` | `add_table(op, name, publication=, role=)`, `render_source_sql(tables, publication, role, app_name=)` |

**App S (sbel-crm).** Replace `sbelcrm/sync/core/` wholesale with imports from `bond_sync_py`. Delete the boundary test for core and
`PORTED_FROM.md` rows; keep the app-side boundary test if you want it. Stays in the app: `routes.py` HOST and handlers, `tables.py`,
`guard.py`, `mirror.py`, `readiness.py`, `errors.py` (service errors mapped through `Host.reject_for`), `bodycap.py` (1 MiB cap on the
upload path; `bond_service_kit.UploadLimit` can replace it), the rate limits, and the REST router `rest/routers/powersync.py`.

**App A (avalon-crm).** `backend/avalon/services/sync_upload.py` splits in two.

| Moves to the lib | Stays in the app |
|---|---|
| `Rejected`, `Skipped`, `Ctx` base fields, `route_for`, `apply`/`upload`, coercion, NUL check, DB-down classifier, logged-bug memory | time policy (`TOO_OLD`, `MAX_DEVICE_OFFSET`, `FUTURE_*`, `as_of`, `parse_device_time`, `BadTime`, `TooOld`) |
| the id check `[A-Za-z0-9_-]{1,64}` | A's own id pattern `^[A-Za-z0-9._:-]{1,200}$` and `det_id`: validate in the handlers, or wrap `apply` |
| `OpResult`, `UploadResponse`, `server_now_iso` | `device_now` in the request and `demo_clock` in the token response |
| | `TIME_TABLES` escalation, `MAX_SENDS`, thread/message handlers, `State` |

## 2. The adapter

- S: `sbelcrm/sync/app/settings.py` becomes a function that builds `SyncTokenSettings(url=..., private_key=...,
  private_key_file=..., kid=..., previous_*=..., audience=..., minutes=...)` from the `POWERSYNC_*` config. Keep the
  `POWERSYNC_*` names in the app; `from_env` is only for apps that adopt `BOND_SYNC_*`.
- A: the request carries `device_now`; the lib's `UploadRequest` forbids unknown fields. Subclass `UploadRequest` in the app
  (`device_now: str`) and pass it to `upload`; the lib reads only `ops`.
- A's `Ctx` has `server_now`, `device_now` and `skew`. Subclass `Ctx` and keep those fields; the lib touches `user` only.
- Settings adapter, `AVALON_SYNC_*` to `SyncTokenSettings`:

| App variable | Field |
|---|---|
| `AVALON_SYNC_URL` | `url` |
| `AVALON_SYNC_JWT_PRIVATE_KEY` | `private_key` |
| `AVALON_SYNC_JWT_PRIVATE_KEY_FILE` | `private_key_file` |
| `AVALON_SYNC_JWT_PREVIOUS_KEY` | `previous_key` |
| `AVALON_SYNC_JWT_PREVIOUS_KEY_FILE` | `previous_key_file` |
| `AVALON_SYNC_JWT_PREVIOUS_KID` | `previous_kid` |
| kid, audience and minutes (read the app's config class for their names) | `kid` (keep `avalon-sync-1` until rotated), `audience`, `minutes` |

## 3. Call-site changes

- S router: catch `DbUnavailable` around `upload(...)` and answer 503 `db_unavailable` with `Retry-After: 5`. `Ctx(user=..., background=...)` is unchanged.
- S: verdict codes the app adds (for example `invalid_phone`) keep working through `reject_for`.
- S publication: call `add_table(op, name, publication="powersync", role="powersync")` in migrations.

## 4. Data

- S: set `kid` explicitly to `sbel-sync-1` while tokens in the wild still carry it, then rotate to the default.
- S: regenerate `sync/sql/01_source.sql` with `render_source_sql(tables, app_name="sbel", generated_by=...)`; the header text changes,
  so the committed file and its equality test change once.
- Apps that rename to `BOND_SYNC_URL`, `BOND_SYNC_PRIVATE_KEY`, `BOND_SYNC_PRIVATE_KEY_FILE`, `BOND_SYNC_KID`,
  `BOND_SYNC_PREVIOUS_KEY`, `BOND_SYNC_PREVIOUS_KEY_FILE`, `BOND_SYNC_PREVIOUS_KID`, `BOND_SYNC_AUDIENCE` and
  `BOND_SYNC_MINUTES` can call `SyncTokenSettings.from_env()` directly.

## 5. Acceptance

1. The app's host passes `fixtures/sync/upload_request_ok.json` through its real route and every result is `ok` or
   the documented verdict (the mixed fixture needs the example's `notes` table; adapt the table name, keep the shapes).
2. `upload_request_dup_seq.json` and `upload_request_too_many_ops.json` answer 422.
3. Every id in `bad_ids.json` `invalid` is a verdict, never a 422; every `ok` id is accepted.
4. A token minted by the app verifies against its own `/jwks.json` with the audience and `kid` the sync service uses.
5. Rotation: with a previous key and its own kid set, both kids appear in the JWKS and an old token still verifies.
6. `upload_response_*.json` parse with the app's response model and re-serialise with unset keys omitted.
7. A database outage during an op answers HTTP 503 `db_unavailable` for the whole request (simulate with an `OperationalError` that has no SQLSTATE).
8. The app's own suite still passes with the core directory deleted.

## 6. Known gaps

Differences from the seeds that apply to both apps:

- `DbUnavailable` replaces re-raising the raw driver error. The route catches it and answers HTTP 503 `db_unavailable` with `Retry-After: 5`.
- The dispatcher closes the session it opened; the seeds left that to the request scope.
- Token settings are a frozen dataclass passed to each call. There is no global `configure(provider)`.
- The default `kid` is `bond-sync-1` and env names are `BOND_SYNC_*`.
- `coerce` also converts DateTime columns (ISO text, trailing Z read as UTC). A bad value is an `invalid` verdict.
- The previous-key problems are reported by `previous_reason(settings)` instead of log lines at startup.
- S: the 503 body `POWERSYNC_OFF` in `rest/routers/powersync.py` stays until the clients move to `{"detail": {"code": "sync_off"}}`.
- A: the dispatcher's stricter id rule would reject A's ids with `.` or `:`. Either keep `apply` in the app for those
  tables or change the id scheme; decide before cutover.
