# bond_tasks_py
Role: tasks table, services, due instants, notice stages and sweep, calendar mirror. Imports only sqlalchemy, pydantic, stdlib.

## Key files
- `models.py` mixin + `TASK_COLUMNS`; `schema.py` input; `service.py` writes; `queries.py` list/summary; `serialize.py` TaskItem
- `due.py` zone arithmetic, `is_overdue`; `permissions.py`, `lifecycle.py`, `hostcols.py`; `today.py`, `links.py`
- Mixins + `*_COLUMNS`: `usersettings.py`, `link_index.py`, `ledger.py`, `outbox.py` (`settings_schema.py` input)
- `stages.py` notice_id/fnv1a31/stages; `quiet.py`; `sweep.py` claim; `outbox.py` deliver; `retention.py`; `compose.py`
- Seams: `protocols.py` (prefs, permissions, links, scheduler, mirror); `notify_protocols.py` (Notice, notifiers)
- `reminders.py` queued reminder (to be retired); `mirror.py`; `sync_routes.py`; `dialect.py` ON CONFLICT insert
- Fixtures in `../../fixtures/tasks/` (task*.json, stage_times.json, notice_ids.json) pin Dart parity
- Rules: `docs/decisions/2026-11-11-due-instant.md`, `2026-11-11-notify-ledger.md`

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`; `make lint`; Postgres tests: `BOND_TEST_POSTGRES_URL=... make test`

## Rules
- No imports from sibling bond_* libs (tests/test_boundary.py enforces). No network in tests.
- Service functions flush, never commit. Datetimes are naive UTC; `due_time` is a local `HH:MM` string.
- 300-line soft cap per source file. No secrets, emails or customer data.
