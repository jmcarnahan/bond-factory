# bond_tasks

The headless task layer for an app that draws its own widgets: models, REST client, a repository seam, a
controller with optimistic complete and undo, notice-stage helpers and time-zone reporting. Pure Dart
(`bond_json`, `bond_api`, `crypto`), no Flutter, no `dart:io`; state is exposed as Streams.

```dart
final api = TasksApi(apiClient); // prefix '/tasks'
final repo = RemoteTaskRepository(api, timeZone: () => deviceZoneName);
final tasks = TaskController(repo)..load();
tasks.states.listen((s) => render(s.open, s.today, s.undoTaskId, s.error)); // replays the current state
tasks.complete('task-1'); // leaves the lists at once; reverts and sets s.error on failure
tasks.undo(); // reopens the last completed task and puts it back
ticker.minutes.listen((_) => tasks.refreshDerived()); // keeps `overdue` from going stale
await repo.create(const TaskDraft(title: 'Send the estimate', dueDate: '2026-03-12', dueTime: '09:30'));
```

## Parts
- Models: `Task` reads and writes exactly the `TaskItem` keys. `dueDate` / `dueTime` are `YYYY-MM-DD` / `HH:MM`
  local wall-clock strings; `dueAt` is the due instant in UTC (null for an undated task or an old server).
  `TaskDraft`, `TaskPatch` (`Present(null)` clears a field), `TaskFilters`, `TaskToday`, `TaskSettings`.
- `TasksApi.parse` returns a `ParseResult` (`items`, `degraded`, `reason`, and `dropped`: how many model items the
  server discarded; show a note when it is above zero). Nothing is created until the user confirms.
- `TasksApi` and `TaskSettingsApi`: the routes. `DemoJobsApi` is for the fake-mode example only.
- `TaskRepository`: the seam under the controller. `RemoteTaskRepository` is the REST version: it passes the
  device's local date and zone on every read, sends `due_at` (UTC, from `deviceDueAt`) only for a timed task,
  and `watchOpen()` re-reads and emits after `refresh()` and after each write made through it (no timer;
  read failures arrive as stream errors). A sync store implements the same interface.
- `TaskController(repo, {clock})`: `states`, `state`, `load()`, `complete(id)`, `undo()`, `refreshDerived()`,
  `dispose()`. `refreshDerived` re-derives `overdue` from `dueAt` and the clock and re-sections the day view
  with `sectionTasks`: overdue (due instant passed), undated, and today (every other open task whose day is
  today or earlier, so a date-only task dated yesterday with its instant still ahead stays there); a later day is in
  no section. Ordered by `dueAt`, nulls last; counts follow; a task is never in two sections. It emits only
  on a change; call it after the calendar day changes too. A failed `complete` puts back only that task. `TaskTicker` gives minute and day ticks.
- Due helpers: `deviceDueAt`, `isOverdue` (open and `dueAt` before now), `dayFor`.
- Stage helpers (`task_stage.dart`): `stageTimes` (the whole schedule in the device zone, each stage with
  `last` and `sendAt`), `stageTimesFor(userId:)` (close and due only for the responsible user, past also for
  the owner), `currentStage`, `stageOf` (`upcoming` / `close` / `due` / `past` for a banner),
  `isSendableNow`, `deadlineToken`, `noticeId`, `fnv1a31`, `inQuietHours`. They use `DateTime(y, m, d, h, min)`
  in the device zone and no zone database; the shared cases are in `fixtures/tasks/stage_times.json`.
  Limit: a date-only task of another user with no `dueAt` lists only the morning stages, because the device
  does not know that user's end of day.
- `ZoneReporter(source, settingsApi).reportIfChanged()`: sends `{time_zone}` when the device zone differs from
  the last value the server accepted (seeded by one settings read); a failed send is retried on the next call.
  `TimeZoneSource` is the seam an app fills with its platform zone lookup.

## Rules
- Words: past its due instant a task is "overdue"; there is no other flag.
- `remind_minutes_before`: `kRemindNone` (-2), `kRemindMorningOf` (-1), `kRemindUseDefault` (-3), or minutes.
- Notice ids match the Python side (`fixtures/tasks/notice_ids.json`).
- Tests: `make test` (it runs in `America/Los_Angeles`, the zone of the stage fixtures).
- A banner is for `TaskStage.close`, `due` and `past` only; `upcoming` and `none` show nothing.
