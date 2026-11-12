# bond_notify_py

Stored notice inbox for the task checklist: one table, a transactional notifier, list/read/dismiss services and
sync routes. SQLAlchemy only. Status: scaffold (0.1.0); stubs raise `NotImplementedError` until they are filled in.

## Table

`NoticesMixin` is the `notices` table: `id` (32 chars, the notice id), `user_id`, `kind`, `title`, `body`, `data`
(JSON: `task_id`, `stage`, `seq`, `due_at`, `priority`, `route`, `actions`, `last`), `source_id` (indexed; the
task id), `created_at`, `read_at`, `dismissed_at`; index `(user_id, created_at)`. No migration ships: the app
creates the table in the same database as `tasks`. `NOTICE_COLUMNS` (name to nullable) is pinned by a test.

```python
class Notice(NoticesMixin, Base): ...
```

## API

- `InboxNotifier(notice_model).write(session, notices)`: a transactional notifier; reads notices by attribute.
- `list_notices`, `mark_read`, `mark_all_read`, `dismiss`, `dismiss_for_source`, `prune_notices`: session in,
  flush, never commit.
- `notice_item(row) -> dict`: the wire `Notice` (see `fixtures/notify/notice.json`), keys in `NOTICE_KEYS`.
- `notice_routes(notice_model, now=...)`: `{("notices", None): NoticeRoute}` for device sync (patch of `read_at`
  and `dismissed_at`).
- `NoticeError(code)`: `notice_not_found` (404), `not_notice_owner` (403).

## Boundary

The lib imports no other bond lib. A notice object is any object with the attributes listed in `NoticeLike`.
