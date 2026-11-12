# bond_notify_py
Role: stored notice inbox (SQLAlchemy 2.0 only; fastapi only in `routes.py`, extra `http`). `tests/test_schema.py` pins the table.

## Key files
- `models.py` `NoticesMixin` + `NOTICE_COLUMNS`; `serialize.py` `notice_item` (wire shape, `NOTICE_KEYS`)
- `notifier.py` `InboxNotifier.write` (set insert, ON CONFLICT DO NOTHING; `dialect.py` picks the dialect)
- `service.py` list (keyset cursor), read, dismiss, dismiss_for_source, prune
- `sync_routes.py` `NoticeRoute`, `notice_routes`, `verdict_for`; `protocols.py` `NoticeLike` (docs only)
- `routes.py` `make_notices_router` (list, read, dismiss, read-all, act via `on_act`)
- fixtures: `../../fixtures/notify/notice.json`, `notices_page.json`

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`
- `make lint`

## Rules
- No imports from sibling bond_* libs, not even for types: a notice is read by attribute (tests/test_boundary.py).
- Service functions take a session, flush, never commit. Datetimes naive UTC; the wire is ISO 8601 with Z.
- The notifier never commits or opens a transaction: it runs inside the sweep's savepoint.
- 300-line soft cap per source file. No secrets, emails or customer data.
