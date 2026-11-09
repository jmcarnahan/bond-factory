# bond_tasks_py
Role: tasks table, services, reminders and calendar mirror. Imports only sqlalchemy, pydantic and stdlib.

## Key files
- `models.py` mixin + `TASK_COLUMNS`; `schema.py` input models; `service.py` writes; `queries.py` list/summary
- `reminders.py` remind_at, schedule, fire; `mirror.py` sync_mirror; `protocols.py` Scheduler/CalendarMirror
- `serialize.py` TaskItem JSON (fixture `../../fixtures/tasks/task.json`); `sync_routes.py` sync handlers

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`
- `make lint`

## Rules
- No imports from sibling bond_* libs (tests/test_boundary.py enforces). No network in tests.
- Service functions flush, never commit. Datetimes are naive UTC; `due_time` is a local `HH:MM` string.
- 300-line soft cap per source file. No secrets, emails or customer data.
