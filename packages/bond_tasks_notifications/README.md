# bond_tasks_notifications

Local phone alerts for tasks (iOS only), the action handler (Done, Snooze, Cancel) and the one
object an app creates: `TaskAlertsCoordinator`.

## What it does
- Schedules the close, due and past notices of every open task as local notifications, so they
  arrive with no network and no app running. Ids are `fnv1a31(noticeId(...))`, the same number the
  server's notice gets, so a notice that also arrives by sync replaces its scheduled copy.
- Keeps the schedule in line with the tasks: a task that is done, cancelled, moved or over budget
  has its alert cancelled. Operations run through one queue and never interleave.
- Applies a tap on a button: Done completes the task, Cancel cancels it, Snooze only puts the
  notice away; the notice is marked read and the phone notification cleared. A failing repository
  call leaves the notice unread so the person can retry.
- A plain tap calls `onOpen(route)`.

## Example
```dart
final coordinator = TaskAlertsCoordinator(
  repository: tasks,                       // TaskRepository
  feed: noticeFeed,                        // NoticeFeed
  plugin: FlutterLocalAlertPlugin(),
  prefs: const TaskPrefs(),
  userId: me.id,
  push: registrar,                         // optional PushRegistrar
  pushTaps: pushTaps,                      // optional PushTaps
  handledElsewhere: {'close', 'due', 'past'}, // only when push is on
  onOpen: (route) => router.open(route),
);
await coordinator.start();
// later, on app resume:
await coordinator.resume();
// ask for permission at a moment you choose (never at launch):
await coordinator.alerts.requestPermission();
// sign-out: unregisters push, cancels every local alert, stops listening
await coordinator.signOut();
coordinator.dispose();   // does not dispose the PushRegistrar: the app owns it
```
An app that turns push on must pass `handledElsewhere: {close, due, past}`, or the person is told
twice. The coordinator never sets it by itself.

## Rules worth knowing
- A synced notice whose scheduled copy already fired is not shown again; a pending copy is
  cancelled and the notice shown now; a stage in `handledElsewhere` is never shown here.
- A notice whose id is among the delivered notifications still shown (`AlertPlugin.active()`) is not
  shown again, so an alert that fired while the app was closed is not doubled after a restart. What
  remains: the person swiped that alert away, the app restarted, and the notice arrives within ten
  minutes; it then shows once more.
- Do not feed a `NoticeController`'s `newUnread` into a second alert path beside the coordinator.
- When the person edits the work day, call `coordinator.updatePrefs(prefs)`.
- A button on a task that no longer exists still clears the notice (`isGone` on the handler).

## Budget
iOS keeps at most 64 pending local notifications. `budget` (60) caps the total and `perTask` (3)
caps one task, nearest first, so one task's daily notices cannot starve the others. A later sync
brings in the ones that did not fit.

## iOS notes
- The permission prompt is not shown at init; call `requestPermission()` when it makes sense.
- Two categories, all buttons opening the app: `bond.task` (`kNoticeCategory`: Done, Snooze) for
  everyone, and `bond.task.owner` (`kNoticeCategoryOwner`: Done, Snooze, Cancel) for the task's
  owner. The category follows the request's actions. An Apple push shows the same buttons only if
  its `category` equals one of these two ids.
- Push and the local-notifications plugin both set the notification-center delegate; see the
  delegate order note in `bond_push`.
- Scheduled alerts go stale if a task changes on the server while the app is closed; push, or the
  next sync when the app opens, corrects it.

## Testing
`FlutterLocalAlertPlugin` talks to platform channels and is not unit-tested; it is kept thin
(every plugin call is in that one file). Everything else is tested through `FakeAlertPlugin`
from `package:bond_tasks_notifications/testing.dart`.
