# bond_sync_py

Server side of device sync: applies a queue of local writes one transaction per op, answers one verdict per op, and mints
the short ES256 tokens a sync service accepts. It knows no table, framework or app.

- `upload(session_factory, host, Ctx(user=...), body)` returns an `UploadResponse`; `.wire()` is the JSON body.
- The app supplies a `Host`: routes per `(table, action)`, tables for coercion, and optional hooks (`reject_for`,
  `already_written`).
- A handler returns nothing (ok) or `Resolved(id)`, or raises `Rejected` or `Skipped`.
- `DbUnavailable` means the database is down; the route answers HTTP 503 `db_unavailable` so the client retries the batch.
- `SyncTokenSettings`, `mint_sync_token`, `jwks` for tokens; `add_table` and `render_source_sql` for the Postgres publication.

Imports only pydantic, PyJWT, cryptography and sqlalchemy. Contract: `docs/contracts/sync_upload.md`.
