# Changelog

## 0.2.0 - unreleased
- Tasks gain `priority` (1 low, 2 normal, 3 high; null clears) and `due_at` (naive UTC, server-computed); index
  `ix_tasks_status_due_at`; `TASK_COLUMNS` updated. `TaskCreate` / `TaskUpdate` accept `priority`, `due_at`
  (a hint) and `time_zone` (write-only); `service.create` / `update` store `priority` so far.
- `TaskItem` has 26 keys (adds `priority`, `due_at`). `task_item` / `task_items` take `now=`: `overdue` is
  then `due_at < now` for an open task (date fallback when `due_at` is not computed); without `now` the old
  date rule still applies.
- `remind_minutes_before` accepts `-3` ("use my default"); the input range is -3 to 525600 as before. The
  default for new rows is still `-2`. `compute_remind_at` returns None for any value below -1, so `-3` queues
  no reminder. `USE_DEFAULT_REMINDER = -3`; `stages.MAX_LEAD_MINUTES = 10080` caps the lead when it is used.
- `due.compute_due_at` rule (not built yet): `due_at` is recomputed only when a write changes `due_date`,
  `due_time` or `assigned_user_id` to a value that differs from the stored one; clearing `due_date` clears it.
- Quiet hours: the "due" stage is always sendable in its 15-minute window; they defer only past stages and the
  close stage of a date-only task. `StageTime` has `send_at`. `deliver_pending` takes `commit` and a notifier
  may return "failed"; the outbox pending index is (`failed_at`, `delivered_at`, `lease_until`).
  `normalize_links` drops repeated (kind, id) pairs; `DefaultPermissions` refuses a missing user id;
  `valid_zone` checks the zone list.
- New error codes `invalid_time_zone` and `invalid_priority` (both 422).
- Zone helpers in `due.py`: `end_of_day_due`, `local_day_bounds`, `next_local_time`, `valid_zone`, and the one
  `is_overdue` definition. `compute_due_at`, `recompute_day_due`, `backfill_due_at` are declared, not yet built.
- New seams: `UserPrefs`, `Preferences`, `Permissions` (`DefaultPermissions`), `LinkResolver`, `AfterWrite`,
  `LINK_KIND_CONTACT`; `notify_protocols` (`Notice`, `STAGES`, `NOTICE_ACTIONS`, `NOTICE_CATEGORY`,
  `TransactionalNotifier`, `Notifier`, `Recipients`, `Compose`).
- New mixins with pinned column lists: `TaskUserSettingsMixin`, `TaskLinkIndexMixin`, `NoticeLedgerMixin`,
  `NoticeOutboxMixin`. `notice_id`, `fnv1a31` and `dialect_insert` are built; the stages, sweep, outbox
  delivery, retention, today view, link and settings services are declared with their final signatures.
- Shared fixtures: `fixtures/tasks/stage_times.json` (with the full stage list per case), `notice_ids.json`.
- Dev extra gains `psycopg[binary]`; pytest marker `postgres` (set `BOND_TEST_POSTGRES_URL`).

## 0.1.0 - unreleased
- `TasksMixin` (table `tasks`), `TaskStatus`, `MirrorStatus`, `TASK_COLUMNS`.
- Service: `create`, `update`, `complete`, `reopen`, `cancel`, `delete`, `get`, `set_checklist_item`, `list_tasks`,
  `summary`, `TaskFilters`, `TaskCreate`, `TaskUpdate`, `TaskError` with coded refusals.
- Reminders: `compute_remind_at`, `schedule_reminder`, `cancel_reminder`, `fire_reminder`, Protocol `Scheduler`.
- Mirror: `sync_mirror`, `remove_event`, `mark_mirror`, Protocols `CalendarMirror`, `MirrorProviders`, `MirrorDraft`.
- Wire shape: `task_item`, `task_items`, `ITEM_KEYS`. Sync: `sync_routes`, `verdict_for`.
