# Release notes: TODO checklist (2026-11)

Pin every module at one commit: the one listed in `docs/sdk/sdk-pins.md`. The adoption order is
`docs/migration/todo-checklist.md`. The wire is `docs/contracts/tasks.md` and `docs/contracts/notices.md`.

## What is new

- Due instant: `tasks.due_at`, server-computed, in UTC, truncated to the minute. A timed task uses the writer's zone and a
  date-only task the responsible user's end of day and zone. A device `due_at` is only a hint and never causes a refusal.
- One meaning of overdue: open and `due_at < now`. Lists, the summary, the Today sections, the calendar lane and the
  widgets agree. An event in the past is "missed".
- `priority` (1 low, 2 normal, 3 high) and per-user settings: `start_of_day` 08:00, `end_of_day` 17:00, `lead_minutes` 60,
  `time_zone`. Quiet hours are derived: after the end of the work day until its start.
- Three-stage notices: close, due and past (one shortly after the due time, then each morning, 5 mornings by default, the
  last one says so). One ledger, one outbox, claimed once across workers, delivered at least once.
- `bond_notify_py` and `bond_notify`, `bond_notify_ui`: a stored inbox with read, dismiss, three actions and a badge.
- `bond_push_py` and `bond_push`: Apple push without Firebase, device rows that sync, and the plugin wiring.
- `bond_capture_py`: a note becomes task and event candidates for review, with a rule-based draft when no model answers.
- `bond_tasks_notifications`: `TaskAlertsCoordinator`, local alerts on the phone with Done, Snooze and Cancel buttons.
- `bond_tasks_powersync` and `bond_notify_powersync`: the task repository, the notice feed and device registration over the
  synced store, so an app works offline.
- Task links: more than one link per task, a link index, and a deleted contact drops the link and keeps the task.
- `bond_ui`: `BondMonthGrid` exported with day markers, `BondSearchPicker`, `BondPersonTile`. `bond_sync_powersync`:
  `waitForUploadDrain` and a testing entry point. `bond_jobs`: `before_every`, `cancel`, `prune`. `bond_calendar`:
  all-day drafts in the app's zone and one forced token refresh on a 401. `bond_api`: error code from `code`, `error_code`
  or a code-shaped `error`.
- Licence: the repository is MIT. Only `services/roof_measure` stays GPL-3.0-or-later.

## What is removed

- The queued single reminder: `reminders.py`, the `Scheduler` protocol, `schedule_reminder`, `fire_reminder`,
  `compute_remind_at`, the columns `remind_at` and `reminded_at`, the wire keys of the same names, and `Task.remindAt` and
  `Task.remindedAt` in Dart. `TaskItem` has 24 keys.

## What an app must do

1. Pin all modules at one commit and run the revision: `tasks.priority`, `tasks.due_at`, drop `remind_at` and `reminded_at`,
   and the six new tables (`task_user_settings`, `task_link_index`, `task_notice_ledger`, `task_notice_outbox`, `notices`,
   `push_devices`). The libs ship no migration.
2. Backfill `due_at` (`backfill_due_at`, or let the first sweep repair rows). The default `remind_minutes_before` of a new
   task is now -3 (use my default). Existing rows keep their value.
3. Run the sweep and `deliver_pending` on an interval, with `since=` set to the activation time. On SQLite call
   `sqlite_savepoint_setup(engine)` once. Delete your reminder job type.
4. Call `dismiss_for_source` on done, cancel and delete, and `dismiss_stale` when a due time changes.
5. Pass `now` (now required) and the viewer zone to `task_item`, `task_items`, `list_tasks` and `summary` (`summary` has no
   `today` argument), and `today()`. Send `time_zone` with client writes.
6. iOS: the Push Notifications capability, the environment from the build (`sandbox` or `production`), the notification
   delegate order, and an Apple key for the server. Android is not supported.
7. With push on, tell the coordinator the three stages are handled elsewhere, or the person is told twice.
8. Provide the model client, contact resolver and spend guard for capture. Spend limits are the app's.

## What is unproven

- Real Apple push delivery, and a tap on a remote notification. The tests use `httpx.MockTransport` and fakes.
- Action buttons on a physical phone. An Apple push carries none: the plugin cannot report which button was pressed.
- PowerSync end to end with a real sync service, and how fast a new notice reaches an open app.
- The browser notification, and the order of the two notification delegates on a device.
- The capture prompt: measured with one small model, one run per phrase, on an easy set.
- The sweep on PostgreSQL above 4 workers or with millions of ledger rows.
