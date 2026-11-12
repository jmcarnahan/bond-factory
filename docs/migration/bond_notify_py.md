# Migrating to bond_notify_py

The stored notice inbox (`libs/bond_notify_py`, SQLAlchemy only): a `notices` table, a transactional notifier the
sweep calls, list, read and dismiss services, retention and sync routes. The ledger, stages and sweep are in
`bond_tasks_py`. The libs meet by shape only and import nothing from each other. Wire: `docs/contracts/notices.md`.
Dart side: `bond_notify.md`. Legend: `docs/migration/README.md`. Order: `todo-checklist.md`.

## 1. What it is

Each claimed stage of a task becomes one row in `notices`, written inside the sweep's claim. A row that is read or
dismissed stays so when the sweep replays. No app has an inbox like this, so nothing is replaced. An app that kept
its own notifications table maps it by hand to `NoticesMixin`.

## 2. What the app adds

- A table. The lib ships no migration. Declare the model in the SAME database as `tasks` (the row is written in the
  claim's savepoint) and write one revision. Assert `NOTICE_COLUMNS` in a test.

```python
class Notice(NoticesMixin, Base): ...
```

- The sweep wiring: `sweep_due(..., transactional=[InboxNotifier(Notice)])`. No outbox row is made for the inbox.
- Routes (all take the signed-in user id, one transaction each):

```python
rows, unread, next_cursor = list_notices(session, Notice, user_id, unread=unread, limit=limit, before=before)
return {"items": [notice_item(r) for r in rows], "unread_count": unread}     # GET /notices
mark_read(session, Notice, user_id, notice_id, now)                          # POST /notices/{id}/read
dismiss(session, Notice, user_id, notice_id, now)                            # POST /notices/{id}/dismiss
mark_all_read(session, Notice, user_id, now)                                 # POST /notices/read-all
```

- `POST /notices/{id}/act` is the app's own. Load the notice, check it is the user's, call
  `apply_notice_action(session, task=task, action=action, actor_user_id=user_id, now=now)` from `bond_tasks_py`,
  mark the notice read, and on done or cancel call `dismiss_for_source(session, Notice, task.id, now)`. Snooze changes nothing on the server and only marks the notice read. Answer
  `{notice, task}`. A cancel by someone who may not is the tasks lib's 403 `not_task_owner`.
- `dismiss_for_source(session, Notice, task_id, now, user_ids=...)` limits the clean-up to those users (after a reassign, the ones who left).
- In the task routes: call `dismiss_for_source` on done, cancel and delete, and
  `dismiss_stale(session, Notice, task_id, task.due_at, now)` when a task's due time changes.
- Errors: `NoticeError` has `code`, `message`, `status`: `notice_not_found` 404, `not_notice_owner` 403, `invalid_cursor` 422.
  Map it to your error body.
- Retention: run `prune_notices(session, Notice, now)` daily. It deletes read or dismissed notices after 30 days and
  every notice after 90 (`read_days`, `max_days`). Sync streams allow no LIMIT, so this keeps the synced set small.

## 3. Smallest working example

A task due at 15:30, a sweep at 15:00 and 15:35, two notices. Run on SQLite (3.35 or later), an in-memory `create_engine("sqlite://")` prepared with
`sqlite_savepoint_setup(engine)` (models: `bond_tasks_py_host.md`):

```python
sweep_due(s, task_model=Task, ledger_model=Ledger, outbox_model=Outbox, now=at,
          prefs=StoredPreferences(Settings), transactional=[InboxNotifier(Notice)]); s.commit()
rows, unread, _ = list_notices(s, Notice, "u1")   # ["Due now: Call back", "Due soon: Call back"], 2
```

## 4. Device sync

`notice_routes(Notice, now=...)` returns `{("notices", None): NoticeRoute}` with `ops={"patch"}` and
`reads=("read_at", "dismissed_at")`. Wrap it as `Route(r.ops, r.handler, r.reads)` and map errors with `verdict_for(exc)`
in the host's `reject_for`. A device may set `read_at` and `dismissed_at` on its own rows. The server stores its own
clock. Another user's row is a `NoticeError`. The stream names `id, user_id, kind, title, body, data, created_at,
read_at, dismissed_at` `WHERE user_id = auth.user_id()`. `source_id` stays server-side.

## 5. What to test

- Assert `NOTICE_COLUMNS` against the engine and round-trip `fixtures/notify/notice.json` through `notice_item`.
- A claim batch whose notifier raises leaves no notice. A replayed sweep inserts nothing and keeps a read notice read.
- `act` with done puts away the task's other notices for every recipient. A cancel by an assignee answers 403.
- A postponed task: the old notices are dismissed and a new one is written for the new time.
- Paging: two pages through `before` give every row once.
- `make -C libs/bond_notify_py test`. With `BOND_TEST_POSTGRES_URL` set the same tests also run on PostgreSQL.

## 6. Known limits

- Notices belong to one user. There is no team inbox, no per-tenant table and no push in this lib (`bond_push_py.md`).
- The notifier compares due times in Python (portable JSON), so very large inboxes of one task are not optimised.
