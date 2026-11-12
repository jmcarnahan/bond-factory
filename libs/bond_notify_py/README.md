# bond_notify_py

Stored notice inbox for the task checklist: one table, a transactional notifier, list/read/dismiss services and
sync routes. SQLAlchemy only (PostgreSQL, and SQLite 3.35 or newer for tests). Version 0.1.0.

## Table

`NoticesMixin` is the `notices` table: `id` (32 chars, the notice id), `user_id`, `kind`, `title`, `body`, `data`
(JSON: `task_id`, `stage`, `seq`, `due_at`, `priority`, `route`, `actions`, `last`), `source_id` (indexed; the
task id), `created_at`, `read_at`, `dismissed_at`; index `(user_id, created_at)`. No migration ships: the app
creates the table in the same database as `tasks`, because the inbox row is written inside the sweep's claim.
`NOTICE_COLUMNS` (name to nullable) is pinned by a test. Datetimes are naive UTC; the wire is ISO 8601 with Z.

```python
class Notice(NoticesMixin, Base): ...

sweep_due(session, ..., transactional=[InboxNotifier(Notice)])   # tasks lib; the notifier is matched by shape
rows, unread_count, next_cursor = list_notices(session, Notice, user_id, unread=True, limit=50)
return {"items": [notice_item(r) for r in rows], "unread_count": unread_count}
```

## How the sweep writes it

`InboxNotifier(Notice).write(session, notices)` is one executemany `INSERT ... ON CONFLICT DO NOTHING` (no
conflict target) keyed by the notice id. It runs inside the sweep's savepoint: it never commits and never opens
a transaction, so a raise anywhere in the batch leaves no notice, and a replayed claim inserts nothing new (a
notice already read or dismissed stays so). Notices are read by attribute (`NoticeLike`); no other lib is imported.

## Services (session in, flush, never commit)

- `list_notices(...) -> (rows, unread_count, next_cursor)`: undismissed rows, newest first by `(created_at, id)`;
  `before` is the cursor of the last row of the previous page. `unread_count` ignores the page.
- `mark_read`, `dismiss` (also reads), `mark_all_read`, `dismiss_for_source(session, Notice, task_id, now)`
  (every user's notices of the task), `prune_notices(session, Notice, now, read_days=30, max_days=90)`.
- The app's "act" route must call `dismiss_for_source` on done and cancel, and deleting a task should call it
  too. Call `dismiss_stale(session, Notice, task_id, due_at, now)` when a task's due time changes (it puts away notices made for any other due instant; None puts away
  all). The notifier does the same for the writing user's task: a notice for a new due instant dismisses the
  live ones of that user and task made for an old instant.
- After a reassignment, `dismiss_for_source(..., user_ids=[old_assignee])` puts away only that user's notices
  of the task (None means everyone; an empty list dismisses nothing).
- Reading or dismissing twice keeps the first stamp. `NoticeError`: `notice_not_found` (404),
  `not_notice_owner` (403), `invalid_cursor` (422).

## Routes an app mounts

`GET /notices` (`unread`, `limit`, `before`), `POST /notices/{id}/read`, `POST /notices/{id}/dismiss`,
`POST /notices/read-all`. `POST /notices/{id}/act` (done, snooze, cancel) is served by `make_notices_router` when the host gives `on_act`: the
host's `on_act` applies the action through the tasks lib and calls `dismiss_for_source` on done or cancel; the router
checks ownership first and marks the notice read.

## Routes

Install with the `http` extra (git form in `docs/sdk/README.md`, "Python": add `extras = ["http"]` to the Poetry line, or pip
`pip install "bond_notify_py[http] @ git+https://github.com/jmcarnahan/bond-factory.git@<sha>#subdirectory=libs/bond_notify_py"`), then `from bond_notify_py.routes import make_notices_router` (the package never
imports it). It serves list, read, dismiss and read-all; with `on_act(session, notice, action, user_id, now)` it also
serves `act`, which checks ownership first. A result key `notice` never replaces the notice. A coded exception (str `code`, str `message`, int `status`) escaping a route is answered as `status` with `{"detail": {"code", "message"}}`; `error_map(exc) -> (status, body) | None` replaces that rule. `session_scope()` is a context manager factory that commits on exit.

## Device sync

`notice_routes(Notice, now=...)` returns `{("notices", None): NoticeRoute}` with `ops={"patch"}` and
`reads=("read_at", "dismissed_at")`; wrap it as `Route(r.ops, r.handler, r.reads)`. A device may set `read_at`
and `dismissed_at` on its own rows only; a value means "mark it now" and the server's clock is stored; a null
clears nothing; another user's row raises `NoticeError`. Map it with `verdict_for(exc)`.

The app's stream names the columns `id, user_id, kind, title, body, data, created_at, read_at, dismissed_at`
with `WHERE user_id = auth.user_id()`. Streams allow no ORDER or LIMIT, so run `prune_notices` regularly: it
is what keeps the synced set small.

Tests run on SQLite; with `BOND_TEST_POSTGRES_URL` set the same tests also run on PostgreSQL (`-m postgres`).
