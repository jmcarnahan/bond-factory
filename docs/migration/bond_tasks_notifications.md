# Migrating to bond_tasks_notifications

Local phone alerts for tasks, the action handler (Done, Snooze, Cancel) and the one object an app creates:
`TaskAlertsCoordinator` (`packages/bond_tasks_notifications`, Flutter, iOS only, needs `bond_tasks`, `bond_notify`,
`bond_push`, `flutter_local_notifications`, `timezone`, `flutter_timezone`). Wire: `docs/contracts/notices.md`.
Legend: `docs/migration/README.md`. Order: `todo-checklist.md`.

## 1. What it replaces

Each app's own reminder scheduling: the code that schedules a local notification per task, cancels it on change, handles a tap
and maps a button to an API call. The coordinator does all of it with one wiring, so no app rebuilds it.

## 2. What it does

- Schedules the close, due and past notices of every open task as local notifications, so they arrive with no network and no
  app running. The id is `fnv1a31(noticeId(...))`, the same number the server's notice gets, so a notice that also arrives
  by sync replaces its scheduled copy.
- Keeps the schedule in line with the tasks: a task that is done, cancelled, moved or over budget loses its alert.
- Applies a button: Done completes the task, Cancel cancels it, Snooze only puts the notice away. The notice is marked read and
  the phone notification cleared. A failing repository call leaves the notice unread so the person can retry.
- Posts a synced notice at once when the app runs, cancels its duplicate, registers the device for push, and routes taps.

## 3. What the app adds

- iOS: nothing for local alerts beyond the delegate order in `bond_push.md`. Two categories are registered by the plugin
  at init: `bond.task` (Done, Snooze) and `bond.task.owner` (Done, Snooze, Cancel). The owner category follows the notice
  actions. All buttons open the app in the foreground.
- A repository and a feed: REST (`RemoteTaskRepository`, `PollingNoticeFeed`) or sync (`PowerSyncTaskRepository`,
  `WatchNoticeFeed`). The coordinator takes the interfaces.
- The permission prompt, at a moment of the app's choosing: `coordinator.alerts.requestPermission()`.
- `TaskPrefs`: the user's work day (`startOfDay`, `endOfDay`, `leadMinutes`, `maxPast`). Call `updatePrefs(prefs)` after a change.
- A route for taps: `onOpen(route)`.

## 4. Smallest working example

```dart
final coordinator = TaskAlertsCoordinator(
  repository: tasks,                          // TaskRepository
  feed: noticeFeed,                           // NoticeFeed
  plugin: FlutterLocalAlertPlugin(),
  prefs: const TaskPrefs(),
  userId: me.id,
  push: registrar,                            // optional PushRegistrar
  pushTaps: pushTaps,                         // optional PushTaps
  handledElsewhere: {'close', 'due', 'past'}, // only when push is on
  onOpen: (route) => router.open(route),
);
await coordinator.start();
await coordinator.resume();                   // on app resume
await coordinator.signOut();                  // unregisters push, cancels every local alert, stops listening
coordinator.dispose();                        // does not dispose the PushRegistrar: the app owns it
```

With push on you MUST pass `handledElsewhere: {'close', 'due', 'past'}`, or the person is told twice. The coordinator never
sets it. The demo uses the coordinator as its only alert wiring.

## 5. Rules worth knowing

- The first feed snapshot is a baseline. A notice older than `freshFor` (10 minutes) is never posted, so a launch does not replay the inbox.
- A synced notice whose scheduled copy already fired is not shown again. A pending copy is cancelled and the notice shown now.
  A notice still among the delivered notifications (`AlertPlugin.active()`) is not shown again.
- Budget: iOS keeps 64 pending local notifications. `budget` (60) caps the total and `perTask` (3) one task, nearest first.
  A later sync brings in the ones that did not fit.
- The same tap reported twice within 3 seconds (the launch tap and the callback on a cold start) is handled once.
- A button on a task that no longer exists (404 or 410) still clears the notice (`isGone`).
- Do not feed a `NoticeController`'s `newUnread` into a second alert path beside the coordinator.
- Scheduled alerts go stale if a task changes on the server while the app is closed. Push, or the next sync, corrects it.
- `NoticeActionHandler(repository, feed, plugin: ...)` is usable alone: `apply(noticeId, taskId, action)`. Use it for the inbox rows
  and the stage banner (`bond_notify_ui.md`, `bond_tasks_ui.md`) so every path behaves the same.

## 6. What to test

- `make -C packages/bond_tasks_notifications test` and `analyze`. Everything but `FlutterLocalAlertPlugin` is tested through
  `FakeAlertPlugin` from `package:bond_tasks_notifications/testing.dart`. The real plugin talks to platform channels and is kept thin.
- With the fake: a moved task cancels its old alert and schedules the new one. Done clears the alert and the notice. Cancel by an
  assignee has no button.
- The simulator lane (`docs/test/MOBILE.md`): permission, one local notification with three buttons, Done, Snooze, Cancel.
- Not provable without a device: a real Apple push, and the order of the two notification delegates on a physical phone.
