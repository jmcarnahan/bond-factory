# Changelog

## 0.1.0 - unreleased
- `Route.optional` (default `()`) and `coerce(..., optional=)`: names in `reads` whose value is blank text or cannot be converted are left out of the data instead of rejecting the op. Every other key is as strict as before.
- `upload` and `apply` take `close_sessions: bool = True`; `False` leaves the session open for a request-scoped factory.
- `upload` takes `now: Callable[[], datetime] | None = None`, the clock behind `server_now` (a naive value is taken as UTC). With `close_sessions=False` on a shared session an accepted op commits the caller's pending work, a rejected op rolls it back.
- `Route.reads` empty means every key is coerced (documented, tested). `DbUnavailable.db_unavailable = True` class attribute.
- Upload envelope (`UploadRequest`, `UploadOp`, `OpResult`, `UploadResponse`), verdict codes and `DbUnavailable`.
- `Route`, `Ctx`, `Host`, `route_for`; `apply` and `upload` (one transaction per op, in seq order).
- Value coercion for device data (bools, JSON text, numbers, ISO datetimes) and the NUL byte check.
- ES256 sync tokens: `SyncTokenSettings` (+ `from_env`, `BOND_SYNC_*`), `mint_sync_token`, `jwks` with a previous key
  during rotation, `load_private_key`, `is_configured`, `key_reason`.
- `add_table` (publication migration helper) and `render_source_sql`, both with the publication, role and app name as parameters.
- Contract: `docs/contracts/sync_upload.md`; fixtures: `fixtures/sync/`.
- Database-down rule: on SQLite only "database is locked" and "unable to open database file" count; other SQLite errors are `server_error` verdicts. Failures in rollback or host hooks become verdicts. Aware datetimes for naive columns are converted to UTC.
