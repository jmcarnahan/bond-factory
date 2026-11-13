# Changelog

## 0.2.0 - unreleased
Added
- `bond_tasks_py.routes.make_tasks_router(...)` (new file; needs extra `http` = fastapi; the package never imports it):
  list, summary, today, get, create, update, complete, reopen, cancel, delete, checklist tick, and settings get/put
  (only with `settings_model`). `error_map(TaskError) -> (status, body)`, `item_extras(task)`, `extra_where_for(request,
  user_id)`, hooks `after_write`, `after_delete`, `after_commit`, `after_delete_commit`, `snapshot`, `on_recomputed`.
  `error_map` must return `(status, body)`; any other return, or a raise, is a `TypeError` naming `error_map`. Include the router after the app's own static `/tasks/<name>` routes. `extra_where_for` narrows the list route only (not `/summary`, `/today`, `/{id}`) and is not a visibility rule.
  Default error body `{"detail": {"code", "message"}}`. `scope=all` and other people's tasks are refused (403
  `forbidden`) unless `read_all_dep` is given. `routes_core.py` holds its fastapi-free rules.
- `task_item(extra=)` / `task_items(extras=)`: keys merged after the 24 item keys; a base key always wins.
- `service.create` / `update` / `sync_routes(prepare=)`: `prepare(session, stored task or None on create, actor user id,
  extras) -> dict` runs after the permission check and before the extras are applied (on update before any field
  changes), on create, update and sync put/patch only (not complete, reopen, cancel, delete or a status-only patch).
  It sees only the extras, filtered to `host_columns`, not the other new values. What it returns is trusted server
  code: every key is stored if it is a column of the task model that is not in `TASK_COLUMNS` (`host_columns` is not
  needed for it); a lib column or an unknown name raises `ValueError`, a non-Mapping raises `TypeError`. A `TaskError`
  it raises writes nothing. None = unchanged.
- `list_tasks(extra_where=())`: a sequence (a single clause raises `TypeError`) of SQLAlchemy criteria on the app's own columns, applied before the count and the paging.
  `TaskFilters.status` also takes `cancelled` and `active` (open and done); an unknown value acts like `all`. An app whose older clients cannot tell a
  cancelled task apart should filter cancelled rows out of its sync stream.
- `task_item(labels=)` takes a Mapping `{(kind, id): label}`, `task_items(labels=)` a callable that gets the page's links and
  returns that Mapping; a label replaces the stored one at read time.
- `sync_routes(fields=)`: narrows the device-writable `FIELDS` columns only; others are dropped like unknown ones.
  Status changes, cancel, delete and `host_columns` extras are not narrowed. A name outside the device set raises `ValueError`.
- App-set work-day defaults: `get_settings(..., defaults=None)`, `StoredPreferences(settings_model, defaults=None)`,
  `update_settings(..., defaults=None)` (a `UserPrefs`; None keeps the old constants; build ONE `StoredPreferences(
  settings_model, defaults)` and pass it to every reader: `prefs=` of `create`, `update` and `sync_routes`, `sweep_due`,
  `backfill_due_at`, `recompute_day_due`; leave `defaults.time_zone` None, `tz=` is the app zone), `settings_overridden(row)`, and
  `settings_item(prefs, warnings=(), overridden=None)` (adds `"overridden"` only when given). `SettingsUpdate` takes null
  on any field to reset it. A reset that changes the effective end of day or zone recomputes due instants too.
- `TASK_USER_SETTINGS_COLUMNS`: `start_of_day`, `end_of_day` and `lead_minutes` are now nullable and the mixin has no
  column default (NULL = follow the app default). Existing stored values stay and read as overridden (a migration may set to
  NULL the values equal to the old constants: 08:00, 17:00, 60). A reset can be refused with `invalid_work_day` when the
  default equals the other stored bound: reset both together. Hosts need a revision that drops NOT NULL on the three columns.

- Sync writes, tolerant reader: `checklist` and `links` sent as JSON text (a phone store writes `"[]"` or `'[{...}]'`) are
  parsed before validation, on put and patch; blank text is not sent; text that is not JSON or not a list is refused like
  any wrong type (`invalid`). A real list works as before. A host needs no `client_json` entry for these two.
- `sync_mirror(transport_pending=False)`: opt-in. When True, a create or update that got no answer from the provider
  (`classify` = `transport`) leaves `mirror_status` `pending` and changes nothing else (pointer, etag, provider kept); the
  next edit retries. Default False: such a failure ends `failed` as before. A provider answer (5xx) is still `failed`, 401
  still `skipped`. Delete paths unchanged. `classify` can now return `transport` (status exactly 0, or a lineage naming
  `TransportError`, `ConnectError`, `TimeoutException`, `ConnectionError` or `TimeoutError`; a non-zero numeric status is
  never transport); it used to return `other` for these, and the default paths treat both the same.
- `sync_mirror(draft_for=)`: `draft_for(session, task, draft)` returns the event to send (body, length, categories,
  reminder), called while the snapshot session is open. If it raises, returns something that is not a `MirrorDraft`, or
  the task's date or time is malformed, the row ends `failed` before any provider call (it used to stay `pending`).
  It must not write: a flush is rolled back, a commit would persist. If it fails during a reassignment the old event
  stays until the next good sync. `failed` is not terminal: the next write sets `pending` again. Default None: unchanged.
- `sweep_due(grandfather_before=)`: a task due before it gets a `skipped` ledger row for every stage (close, due, past
  up to `max_past`), so no later pass claims it. `backfill_due_at(open_only=)` leaves done and cancelled tasks alone.
- `Notice.attempt` (default 1): `deliver_pending` sets it from the outbox row's existing `attempts` counter (1 first,
  +1 for each later lease). No column change. `deliver_pending(at_most_once=)`: for those channels `delivered_at` is
  stamped and committed BEFORE the send; a send that then fails or raises, and any early failure, also sets `failed_at`.
- `service.create` / `update`: with `prefs` given and no zone sent and no `writer_zone`, a timed task uses the actor's
  stored zone (`prefs.for_user(session, actor).time_zone`); an empty zone falls through to `tz`.
  The lookup is lazy: a write that does not compute `due_at` (a title-only update, a task with no date) never
  reads `prefs`.
- `sync_routes(on_deleted=)`: `on_deleted(ctx, session, task_id, owner_user_id)` runs after every real delete
  (mirrored or not), so a host can put away the task's notices. `after_delete` is unchanged.

- `update_settings(..., on_recomputed=None)` and `recompute_day_due(..., on_recomputed=None)`:
  `on_recomputed(task, old_due_at)` runs once per task whose `due_at` really changed, after the flush (the host calls
  `dismiss_stale`). `notice_recipients(task) -> set[str]`: owner and assignee, for putting away the notices of users
  who left after a reassign.
- `apply_notice_action` "done" or "cancel" on a task that is not open is a no-op returning the task.
- A `due_at` that does not parse is dropped by `TaskCreate` / `TaskUpdate` (it is only a hint), never a 422.
- `MirrorDraft.leave: frozenset[str] = frozenset()` (a list, tuple or set is accepted and normalised; None is empty; a str is a `ValueError`): names of draft fields an UPDATE must not send (the person keeps them in
  their own calendar, for example `location`, `categories`, `reminder_minutes`). A create, including the one after a not-found
  update, sends every field; the etag re-read path sends the same reduced patch. `leave` is never a payload key. An unknown
  name, or `start`/`end`/`is_all_day` not left together, is a `ValueError` at construction (a bad `draft_for` result: the
  row ends `failed`). The default sends all fields as before. A task's own change to a left field is not propagated.
- `TaskRoute.optional` (new 4th field, default `()`): on `("tasks", None)` it lists `due_at`, `priority` and
  `remind_minutes_before` (those in `fields`). A host that passes it on (`Route(r.ops, r.handler, r.reads, r.optional)`) has
  the dispatcher leave a blank or unreadable (not only blank) value of those keys out, with no verdict, instead of rejecting the op, so an unreadable `due_at`
  hint keeps its promise and an old client's `priority: ""` is "not sent". "Blank or unreadable" is deliberate (approved): an unreadable non-blank `priority` is also left out. A host that does not pass it behaves as before.
  `_fields` also treats a blank `priority` / `remind_minutes_before` as not sent. A readable priority outside 1 to 3 is
  still `invalid_priority`.
- `sync_routes`: `complete`, `reopen` and `cancel` routes have `reads=NO_READS` (`("",)`, a name no column has) instead of `()`,
  which coerced every key: an unreadable key the handler ignores (an old client resending `completed_at: "garbage"`) no longer
  rejects the op.
- `models.reminder_setting(task)`: a NULL `remind_minutes_before` (a column added to old rows) reads as `USE_DEFAULT_REMINDER` in `stages` (`stage_times`, `current_stage`, the sweep), the mirror draft and `task_item`; it raised `TypeError` before.

Changed (breaking)
- `now` is required (keyword): `task_item(task, *, today, now, names=None)`, `task_items(tasks, *, today, now,
  names=None)`, `list_tasks(..., viewer_zone=None, now)`, `summary(session, *, task_model, user_id, now,
  viewer_zone)` (`today` and the date-only counts are gone). The legacy date-based overdue path is removed.
- `sync_routes` raises `TaskError("invalid_priority")` (422) for a priority outside 1 to 3 on put or patch
  (before, a bare validation error).

Removed
- The queued single reminder: `reminders.py`, `compute_remind_at`, `schedule_reminder`, `cancel_reminder`,
  `fire_reminder`, `dedupe_key`, `JOB_TYPE`, the `Scheduler` protocol and `sync_routes(scheduler=)`. The three-stage
  sweep replaces it.
- The columns and wire keys `remind_at` and `reminded_at` (`TASK_COLUMNS`, `ITEM_KEYS`). `TaskItem` has 24 keys.
- Changed: the default `remind_minutes_before` of a new task is -3 (use my default), in the column and in
  `TaskCreate`; an explicit value is kept.

Due instant
- Tasks gain `priority` (1 low, 2 normal, 3 high; null clears) and `due_at` (naive UTC, minute precision, null only
  when `due_date` is null); index `ix_tasks_status_due_at`; `TASK_COLUMNS` updated. `TaskCreate` / `TaskUpdate`
  accept `priority`, `due_at` (a hint) and `time_zone` (write-only, never stored on the task).
- `compute_due_at`: a timed task uses the writer's zone (sent, else stored, else app default); a date-only task
  uses the responsible user's end of day and zone. A client `due_at` is honoured only for a timed task, only as a
  whole-quarter-hour offset within -12:00 to +14:00; `compute_due_at` gained `sent_zone`, and a hint is checked
  only against a zone sent with the same write (the stored zone never rejects it); else ignored, never refused.
  `update` recomputes only when the date, time or assignee differs from the stored value (a reassignment moves a
  date-only task only); clearing `due_date` clears `due_at`. Nonexistent local times move forward, ambiguous take
  the first occurrence.
- One overdue definition, `is_overdue(task, now, viewer_today=None)`: open and `due_at < now`; a dated task with no
  `due_at` yet falls back to its date before `viewer_today`. `task_item` / `task_items` take `now=`; without it the
  old date rule applies. `TaskItem` has 26 keys (adds `priority`, `due_at`).
- Zone helpers: `end_of_day_due`, `local_day_bounds`, `next_local_time`, `valid_zone` (checks the zone list),
  `recompute_day_due`, `backfill_due_at`.
- New error codes `invalid_time_zone`, `invalid_priority`, `invalid_work_day`, `invalid_action`.

Permissions and app columns
- Seams `Permissions` and `DefaultPermissions` (owner or assignee edits; owner deletes, cancels, reassigns; a
  missing user id can do nothing). `update`, `complete`, `reopen`, `cancel`, `delete` and
  `set_checklist_item` accept `permissions`. `apply_notice_action` (done, snooze, cancel; else `invalid_action`).
- `apply_extras` and `host_columns`: app columns pass through create, update and sync by an allow-list; an unknown
  allow-listed column is a `ValueError`. Input models still refuse unknown fields.
- `AfterWrite` `(session, task)` runs after the flush in `create` and `update`. `create` takes no `permissions`.

Today and summary
- `today(...)` returns `TodayResult`: overdue, today, undated, done today, with counts. `list_tasks` takes
  `viewer_zone` (instant ordering, date ranges as local days), `link_index_model` and `now`. `summary` takes `now`
  and `viewer_zone` and uses the same overdue test; `viewer_today` is exported. TODAY (`queries.due_today_sql`,
  used by `today`, `summary` and list ranges) is every open task that is not overdue and whose day is the viewer's
  today or earlier.

Links
- `TaskLinkIndexMixin` and `TASK_LINK_INDEX_COLUMNS`; `reindex_links`, `make_link_hook`; the link filter becomes an
  indexed lookup with SQL paging when `link_index_model` is passed. `LinkResolver`, `LINK_KIND_CONTACT`.
  `retarget_links` (merge) and `remove_links` (delete). `normalize_links` drops repeated (kind, id) pairs.

Settings
- `TaskUserSettingsMixin`, `TASK_USER_SETTINGS_COLUMNS`, `UserPrefs`, `Preferences`, `StoredPreferences`,
  `get_settings`, `update_settings` (recomputes date-only `due_at` when `end_of_day` or `time_zone` changes; warning
  `lead_longer_than_work_day`, and `time_zone_unknown` when the work day changed and no zone is stored), `SettingsUpdate`, `settings_item`. Quiet hours are derived, never stored.

Stages, sweep, outbox, retention
- `remind_minutes_before` accepts `-3` ("use my default"); range -3 to 525600. `USE_DEFAULT_REMINDER = -3`. The
  model column and `TaskCreate` default is still `-2`. `compute_remind_at` returns None below -1, so the old
  queued reminder queues nothing for `-3`. The lead is capped at `MAX_LEAD_MINUTES = 10080` when used.
- `stage_times`, `current_stage`, `StageTime` (with `send_at`), `notice_id`, `fnv1a31`, `deadline_token`,
  `effective_zone`; stages close, due (15 minutes), past (one, then each morning, `max_past=5`).
- Quiet hours (`in_quiet_hours`, `next_work_start`, `sendable`): the due stage and the close stage of a timed task
  always send; past stages and the close stage of a date-only task wait for the work day.
- `NoticeLedgerMixin`, `NoticeOutboxMixin` and their `*_COLUMNS`; `sweep_due` (set-based claim, one savepoint,
  row-by-row retry with ledger status "error", `since` records older stages as "skipped", repairs missing
  `due_at`; an idle sweep issues no INSERT; `Recipients` is asked only for the current stage; a row whose notifier
  fails alone is not recorded, the next sweep retries it, `SweepResult.errors` counts it), `SweepResult`, `default_recipients`, `default_compose`, `dialect_insert` (PostgreSQL and SQLite).
  `TransactionalNotifier`, `Notifier` ("ok", "retryable", "unregistered", "failed"), `Recipients`, `Compose`,
  `Notice`, `STAGES`, `NOTICE_ACTIONS`, `NOTICE_CATEGORY`.
- `deliver_pending(..., commit=, task_model)` (required keyword; `None` skips the check): exact `limit`, lease committed before any send, then send, stamp
  and commit per row; at-least-once; `now` may be aware. With `task_model`, a row whose task is gone, closed or
  postponed is stamped failed "superseded" (`DeliverResult.superseded`). `DeliverResult.unrouted` counts pending rows
  of a channel with no notifier; they fail after 7 days.
- The sweep checks the ledger before composing; outbox inserts are chunked under 900 bind parameters; the claim
  needs SQLite 3.35 or later (`RETURNING`).
- `prune_ledger` (old-deadline candidates read in pages) deletes finished-task rows, close and due rows after 8 days, superseded past rows after 2 days, and
  rows of an old deadline after 8 days.
- `stage_times` omits an impossible "past 0"; `past_days` is a window by start time; past numbers are decided by
  instants; `in_quiet_hours` compares at minute precision.
- `ensure_savepoint_safe(session)` (exported) is called first by `sweep_due` and `deliver_pending`; it raises
  `RuntimeError` on a SQLite engine not prepared with `sqlite_savepoint_setup`.
- `list_tasks` and `today` show only the viewer's own tasks (owner or assignee) unless `TaskFilters.scope="all"`,
  which the app must gate.
- `sqlite_savepoint_setup(engine)` (isolation_level None plus explicit BEGIN) for SQLite; exported with
  `settings_item`, `effective_zone`, `sendable`, `default_recipients`, `viewer_today` and `MAX_LEAD_MINUTES`.

Sync
- `sync_routes` accepts `source` on put, ignores a patch that carries only a `due_at` hint, takes `link_index_model` (with
  `service.delete`, the task's link-index rows go with the task) and gains `zone_of`, `prefs`, `permissions`, `host_columns`, `link_hook`, adds the `cancel` route, and
  treats a malformed device `due_at` as absent. `scheduler` is optional.

Tests and fixtures
- Shared fixtures `fixtures/tasks/stage_times.json`, `notice_ids.json`. Dev extra gains `psycopg[binary]`; pytest
  marker `postgres` (set `BOND_TEST_POSTGRES_URL`).

## 0.1.0 - unreleased
- `TasksMixin` (table `tasks`), `TaskStatus`, `MirrorStatus`, `TASK_COLUMNS`.
- Service: `create`, `update`, `complete`, `reopen`, `cancel`, `delete`, `get`, `set_checklist_item`, `list_tasks`,
  `summary`, `TaskFilters`, `TaskCreate`, `TaskUpdate`, `TaskError` with coded refusals.
- Reminders: `compute_remind_at`, `schedule_reminder`, `cancel_reminder`, `fire_reminder`, Protocol `Scheduler`.
- Mirror: `sync_mirror`, `remove_event`, `mark_mirror`, Protocols `CalendarMirror`, `MirrorProviders`, `MirrorDraft`.
- Wire shape: `task_item`, `task_items`, `ITEM_KEYS`. Sync: `sync_routes`, `verdict_for`.
