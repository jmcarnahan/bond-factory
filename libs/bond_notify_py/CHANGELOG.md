# Changelog

## 0.1.0 - unreleased
- `NoticesMixin`, `NOTICE_COLUMNS`, `notice_item`, `NOTICE_KEYS`, `NoticeError`, `NoticeLike`.
- `InboxNotifier` (set-based insert, target-less ON CONFLICT DO NOTHING, title truncated to 255).
- `list_notices` (keyset cursor on `(created_at, id)`), `mark_read`, `mark_all_read`, `dismiss`,
  `dismiss_for_source`, `prune_notices`.
- `notice_routes` (device patch of `read_at` and `dismissed_at` on own rows), `NoticeRoute`, `verdict_for`.
- `dismiss_stale`; `InboxNotifier` puts away live notices made for an old due instant of the same user and task.
- Postgres lane: every service test also runs on PostgreSQL when `BOND_TEST_POSTGRES_URL` is set.
- Error code `invalid_cursor` (422).
