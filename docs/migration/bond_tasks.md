# Migrating to bond_tasks

The headless task layer (`packages/bond_tasks`, pure Dart: `bond_json`, `bond_api`, `crypto`, no Flutter, no `dart:io`).
Models, REST client, a repository seam, a controller with optimistic complete and undo, due and stage helpers, zone
reporting. Widgets are in `bond_tasks_ui.md`. Server half: `bond_tasks_py.md`. Wire: `docs/contracts/tasks.md`.
Legend: `docs/migration/README.md`. Order: `todo-checklist.md`.

## 1. What it replaces

| App | Goes away | Becomes |
|---|---|---|
| S web and phone | `task_models.dart`, `task_api_service.dart`, the task widgets (see `bond_tasks_ui.md`) | `Task`, `TaskDraft`, `TaskPatch`, `TaskFilters`, `TasksApi`, `TaskController` |
| A | `PersonalEvent`, `EventDraft`, `EventInput` (personal events) | tasks with a due date and optional time |

S keeps its LLM parse mapping app-side or moves to `TasksApi.parse` (`bond_capture_py.md`). A keeps its day layout.

## 2. Headless use (no `bond_ui`)

The package draws nothing. State is Streams. This is a complete screen-less client:

```dart
final api = TasksApi(apiClient); // prefix '/tasks'
final repo = RemoteTaskRepository(api, timeZone: () => deviceZoneName);
final tasks = TaskController(repo)..load();
tasks.states.listen((s) => render(s.open, s.today, s.undoTaskId, s.error)); // replays the current state
await repo.create(const TaskDraft(title: 'Send the estimate', dueDate: '2026-03-12', dueTime: '09:30'));
tasks.complete('task-1'); // leaves the lists at once; reverts and sets s.error on failure
tasks.undo();
ticker.minutes.listen((_) => tasks.refreshDerived()); // keeps `overdue` and the sections from going stale
```

The app supplies: the zone name (`timeZone:`), a `TimeZoneSource` for `ZoneReporter(source, TaskSettingsApi(client))`
and a call to `reportIfChanged()` at start and resume, and `TaskTicker` (minute and day ticks) wired to `refreshDerived`.

## 3. What changed for existing callers

| Old | New |
|---|---|
| `Task.remindAt`, `Task.remindedAt` | removed with the single reminder (`remind_at`, `reminded_at` are not on the wire). `Task.fromJson` still reads a missing `remind_minutes_before` as -2 |
| date-based `overdue` | `isOverdue(task, nowUtc)`: open and `dueAt` before now. The server flag follows the same rule |
| `remindMinutesBefore` default | `kRemindUseDefault` (-3). Others: `kRemindNone` (-2), `kRemindMorningOf` (-1), minutes |
| (none) | `Task.priority` (1 to 3), `Task.dueAt` (UTC), `TaskSettings`, `TaskToday`, `ParseResult` |
| `status == 'open'` | `task.isOpen` and the `TaskStatus` enum |

`dueDate` and `dueTime` are local wall-clock strings (`YYYY-MM-DD`, `HH:MM`). Never convert them to UTC on the client
except through `deviceDueAt`, which the repository already uses. It sends `due_at` only for a timed task, computed in the
device's current zone, and none for a date-only task. `RemoteTaskRepository` sends the device date and zone on every read.

## 4. Stage helpers

`task_stage.dart` computes the same stages as the server, in the device zone, with no zone database:
`stageTimes`, `stageTimesFor(userId:)` (close and due for the responsible user, past also for the owner),
`currentStage`, `stageOf` (`upcoming`, `close`, `due`, `past`, for a banner), `isSendableNow`, `inQuietHours`,
`deadlineToken`, `noticeId`, `fnv1a31`. `TaskPrefs(startOfDay, endOfDay, leadMinutes, maxPast)` mirrors the settings.
The cases are shared with Python in `fixtures/tasks/stage_times.json` and `notice_ids.json`.
Limit: a date-only task of another user with no `dueAt` lists only morning stages, because the device does not know
that user's end of day.

## 5. Data and calls

- Tasks are rows of `tasks` (`bond_tasks_py`). Ids: a client may choose `^[\w-]{1,64}$`. Replaying a create returns the
  row. Another owner's id answers 409 `id_taken`.
- `TaskError`-style codes arrive as `bond_api` exceptions: `NotFound` (`task_not_found`), `Forbidden`
  (`not_task_owner`, `not_task_editor`), `Conflict` (`id_taken`), `ValidationError`. Cancel and undo of a cancel are owner-only.
- `TaskPatch` with `Present(null)` clears `notes`, `due_date`, `due_time`, `assigned_user_id` and `priority`.
- `TasksApi.parse` returns `ParseResult` (`items`, `degraded`, `reason`, `dropped`). Nothing is created until the
  user confirms. `DemoJobsApi` (fake-mode tick only, no notices call any more) is for the example. Do not call it from an app. `RemoteTaskRepository` sends `today` only when it has no time zone.
- With a sync store, use `PowerSyncTaskRepository` instead of `RemoteTaskRepository` (`bond_tasks_powersync.md`). The
  controller does not change.

## 6. Acceptance

- `make -C packages/bond_tasks test` (it sets TZ=America/Los_Angeles) and `analyze`.
- Round-trip `fixtures/tasks/task.json` through `Task.fromJson` and `toJson`.
- Test with a fake `TaskRepository`: complete then undo, a failed complete restoring only that task, and
  `refreshDerived` moving a task from today to overdue when the clock passes `dueAt`.
- In the app: its task tests pass against the adapter, then the full suite once before the PR.

## 7. Known gaps

- No quick-add text parsing, no inline editor, no loan picker: they stay in the app.
- A: all-day events with an end time lose the end. Multi-day events are not tasks.
- `TaskStatus.cancelled` is on the wire. The widgets show it as a done-style row.
