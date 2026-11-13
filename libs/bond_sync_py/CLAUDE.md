# bond_sync_py
Role: server side of device sync: applies a queue of local writes one transaction per op, answers one verdict per op, mints ES256 sync tokens. Contract: `docs/contracts/sync_upload.md`; fixtures: `fixtures/sync/`.

## Key files
- `envelope.py` wire models (`UploadRequest` <= 100 ops, unique seq; `OpResult`; `server_now_iso`); `verdicts.py` codes, `Rejected`/`Skipped`/`Resolved`, `DbUnavailable`, database-down classifier
- `routes.py` `Route` (`reads`, `optional`), `Ctx`, `Host`, `route_for`; `dispatcher.py` `apply` / `upload` (one transaction per op, seq order)
- `coerce.py` device values to server types (`optional=` keys dropped when unreadable), NUL check; `replay.py` `LoggedBugs`, `written_by`
- `tokens.py` `SyncTokenSettings`, `mint_sync_token`, `jwks`, key loading; `publication.py` `add_table`; `source_sql.py` `render_source_sql`

## Tests
- `test_fixtures.py`, `test_mixed_pair.py` (fixture pair through `upload`), `test_dispatcher.py` (every verdict, database-down escape), `test_coerce.py`, `test_tokens.py` (mint, JWKS, clamp, rotation), `test_publication.py`, `test_boundary.py` (imports)

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`
- `make lint`

## Rules
- Imports only pydantic, PyJWT, cryptography, sqlalchemy and the standard library (`test_boundary.py`). No sibling bond_* libs.
- Only an unavailable database escapes (`DbUnavailable`); every other failure is a per-op verdict.
- No network in tests. 300-line soft cap per source file. No secrets, emails or customer data.
