# Adopting the TODO checklist

One order for an app that wants due times, three-stage notices, an inbox, Apple push, natural-language capture and
phone alerts. Each step lands on its own, so stop after any of them. Take every bond module at one full commit id
(`docs/sdk/README.md`). The wire is in `docs/contracts/tasks.md` and `docs/contracts/notices.md`. Release notes:
`docs/sdk/release-2026-11-todo.md`. Legend and common procedure: `docs/migration/README.md`.

The words are fixed. A task past its due instant is **overdue** and that is the only flag. An event in the past is **missed**.
Phones are iOS only.

## What changed on 2026-11-12

Seams added after the first release, all defaulting to the old behaviour. Read these before you write the adapter:
`bond_tasks_py.md` and `bond_tasks_py_host.md` (`prepare`, `extra_where`, `labels`, `grandfather_before`, `draft_for`,
work-day defaults with the `overridden` answer and the nullable columns), `bond_notify_py.md` (`get_owned` first in an act
route), `bond_sync_py.md` (`now=`), `bond_jobs.md` (`run_schedule`), `bond_service_kit.md` (`fake_clock_router`),
`bond_tasks.md` and `bond_tasks_powersync.md` (`Task.extras`, the enricher, the clock levers), `bond_push_apple.md` and
`bond_auth_secure_storage.md` (the splits). Wave B: the router factories, rich capture and `BondShape` (list in `docs/migration/README.md`). The index is in `docs/migration/README.md`.

## Before you start

- Adopt `bond_tasks_py` and `bond_tasks` first, or in the same step. Everything below sits on them.
- Decide where the sweep runs: a `bond_jobs` tick or a plain interval script (`bond_tasks_py.md` section 5).
- Decide the zone: the app default (`tz`) is used for a user with no stored zone.

## Backend

1. **Tables and the sweep** (`bond_tasks_py.md`). One revision: the new `tasks` columns (`priority`, `due_at`), drop
   `remind_at` and `reminded_at`, and add `task_user_settings`, `task_link_index`, `task_notice_ledger`,
   `task_notice_outbox`. Mount the task routes (list, summary, today, CRUD, lifecycle, settings): `bond_tasks_py_host.md` gives each route and its service call, and or mount `bond_tasks_py.routes.make_tasks_router` (extra `http`); the reference host is `services/sdk_example/sdk_example/routes/task_routers.py`. Pass `now` and the viewer zone. On SQLite call `sqlite_savepoint_setup`.
   Run `sweep_due` with `since=` set to the activation time. Backfill with `backfill_due_at` or let the sweep repair rows.
   Check: a task due in two minutes yields a ledger row at the right stage, and a second sweep claims nothing.
2. **Inbox** (`bond_notify_py.md`). Add the `notices` table beside `tasks`, list `InboxNotifier(Notice)` in
   `transactional=`, mount `GET /notices`, read, dismiss, read-all and `act`. Call `bond_notify_py.dismiss_for_source` on done, cancel and
   delete (it lives in `bond_notify_py`, as does `dismiss_stale`). Run `prune_notices` daily. Check: each stage writes one notice, and done puts the rest away.
3. **Push** (`bond_push_py.md`). Add `push_devices`, the device routes (REST or sync) and `PushNotifier` with an
   `ApnsSender`, and list the `"push"` channel only when the key is configured. Run `deliver_pending` after each sweep.
   Check with `MockSender` first. A real delivery needs an Apple key and a device.
4. **Capture** (`bond_capture_py.md`). Write the `LlmClient`, the contact `EntityResolver` and the spend `CaptureGuard`, then
   mount `POST /tasks/parse`. Check with `llm=None`: one degraded draft. Model spend limits are the app's.

## Dart, headless first

5. **Headless layer** (`bond_tasks.md`, `bond_notify.md`). `TasksApi`, `RemoteTaskRepository`, `TaskController`,
   `ZoneReporter`, `TaskTicker`, `NoticesApi`, `PollingNoticeFeed`, `NoticeController`. This is a full client with no
   widgets and no `bond_ui`: render the streams yourself. Check the controller against a fake repository.
6. **Widgets** (`bond_tasks_ui.md`, `bond_notify_ui.md`, `bond_ui.md`). The Today list, the form, the stage banner, capture
   review, settings form, inbox list and badge. Needs the `bond_ui` theme and labels. Skip this step for a custom UI.
7. **Alerts coordinator** (`bond_tasks_notifications.md`, `bond_push.md`). One `TaskAlertsCoordinator` with the repository, the
   feed, `FlutterLocalAlertPlugin` and, if push is on, the registrar and taps with `handledElsewhere` set. On iOS: the delegate
   order, the Push Notifications capability and the environment (`sandbox` for debug, `production` for release).
   Check in the simulator (`docs/test/MOBILE.md`): permission, a local notification with three buttons.
8. **Sync adapters** (`bond_sync_powersync.md`, `bond_tasks_powersync.md`, `bond_notify_powersync.md`). Only for an app that
   syncs. Add the tables and streams, swap in `PowerSyncTaskRepository`, `WatchNoticeFeed` and `SyncPushDevices`, and mount
   `sync_routes`, `notice_routes` and `device_routes` on the upload side. Sign out in this order: unregister the device,
   `waitForUploadDrain`, disconnect, clear.

## Rules that cross steps

- One id on every path: `notice_id`, computed the same in Python and Dart (`fixtures/tasks/notice_ids.json`). Delivery is at
  least once, so every channel must be idempotent on it.
- The three actions (Done, Snooze, Cancel) go through one handler on the inbox row, the banner and the phone button.
- The Dart stage functions use the device zone and Python the user's stored zone. Before `ZoneReporter`'s report lands, local alert ids can differ from server ids and a duplicate alert is possible.
- Do not run two alert paths. With push on, tell the coordinator the three stages are handled elsewhere.
- No popups, dialogs or sheets. The widgets expand inline.
- Pin every module at the same commit: the one listed in `docs/sdk/sdk-pins.md`.

## Order of testing

1. Per module: `make -C <module> test` and `analyze` or `lint`.
2. In the app: its task tests against the adapter, then the full suite once, before the PR.
3. The web walk (`docs/test/WEB.md`) with the fake-clock tick, then the simulator lane (`docs/test/MOBILE.md`).
4. Unproven until you do it: Apple push on a device, PowerSync end to end, and the browser notification.
