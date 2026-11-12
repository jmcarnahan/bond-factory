# bond_tasks_py
Role: tasks table, services, due instants, notice stages, sweep, outbox, calendar mirror. Imports only sqlalchemy, pydantic, stdlib.

## Key files
- `models.py` mixin + `TASK_COLUMNS`; `schema.py` input; `service.py` writes; `queries.py` list/summary; `serialize.py` TaskItem
- `due.py` zone arithmetic, `is_overdue`; `permissions.py`, `lifecycle.py`, `hostcols.py`; `today.py`, `links.py`
- Mixins + `*_COLUMNS`: `usersettings.py`, `link_index.py`, `ledger.py`, `outbox.py` (`settings_schema.py` input)
- `stages.py` notice_id/fnv1a31/stages; `quiet.py`; `sweep.py` + `sweep_claim.py` claim; `outbox.py` deliver; `retention.py`; `compose.py`
- Seams: `protocols.py` (prefs, permissions, links, mirror); `notify_protocols.py` (Notice, notifiers)
- `mirror.py` (`draft_for` hook); `sync_routes.py`; `dialect.py` ON CONFLICT insert, `sqlite_savepoint_setup`, `ensure_savepoint_safe`
- Fixtures in `../../fixtures/tasks/` (task*.json, stage_times.json, notice_ids.json) pin Dart parity
- Rules: `docs/decisions/2026-11-11-due-instant.md`, `-notify-ledger.md`, `-links.md`

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`; `make lint`; Postgres tests: `BOND_TEST_POSTGRES_URL=... make test`

## Rules
- No imports from sibling bond_* libs (tests/test_boundary.py enforces). No network in tests.
- Service functions flush, never commit. Datetimes are naive UTC; `due_time` is a local `HH:MM` string.
- Every `*_COLUMNS` change needs a CHANGELOG line; keep the README at most 120 lines.
- 300-line soft cap per source file. No secrets, emails or customer data.
