# legacy_host
Role: TEST-ONLY host of an app that already exists: legacy column names, app-owned columns, a legacy REST wire, tables that pre-date the modules. Never shipped. The new-build counterpart is `services/sdk_example`.

## Key files
- `legacy_host/models.py`: mixins attached with renamed columns (`Task`, `ShareGrant`, `UserPrefs`) and the app's columns; `HOST_COLUMNS`.
- `rules.py`: `prepare` (blank to NULL, only owner/admin relinks, case implies client), `LegacyPermissions`.
- `wire.py` (`legacy_item`, `legacy_error`), `bodies.py` (both request vocabularies), `routes.py` (own task routes over `service.*`), `routes_extra.py` (`/prefs`, `/shares`), `app.py`, `deps.py`.
- `legacy_ddl.py`: the old tables as raw DDL and the `ADOPT` migration; `tests/legacy_db.py` builds a database from them.
- `README.md`: trait -> test file. Fixtures: `../../fixtures/legacy_host/`.

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_legacy_wire.py`; `make lint`; `BOND_REGEN_FIXTURES=1 make test T=tests/test_new_client_wire.py` rewrites the recorded answers.

## Rules
- Workspace sources allowed here only. No network in tests. Only `*@example.com`, no app or brand names, no real data.
- Auth is the header `X-User: <id>`; the clock is frozen at 2026-11-08 10:00 UTC in `conftest.py`.
- Do not fix a lib here: pin the limit in a test named for it (`xfail(strict=True)` while it fails) and report the gap.
- 300-line soft cap per source file.
