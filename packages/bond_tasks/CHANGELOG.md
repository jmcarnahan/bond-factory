# Changelog

## 0.2.0 - unreleased
Removed
- `Task.remindAt` and `Task.remindedAt` (and the `remind_at`, `reminded_at` wire keys); the queued reminder is gone.
- Changed: `TaskDraft.remindMinutesBefore` defaults to -3 (`kRemindUseDefault`).

- `Task.priority` (`TaskPriority`) and `Task.dueAt` (keys `priority`, `due_at`, right after `due_time`);
  `TaskDraft` and `TaskPatch` gain `priority`, `dueAt`, `timeZone`; `TaskFilters.timeZone`; `kRemindUseDefault` (-3);
  `Task.copyWith`.
- `TaskToday`, `TaskTodayCounts`; `ParseResult`, `CaptureItem` (`TaskCandidate`, `EventCandidate`), `LinkCandidate`,
  `LinkOption`; `TaskSettings`, `TaskSettingsPatch`, `TaskSettingsApi`; `LinkSearch`; `TimeZoneSource`, `ZoneReporter`.
- `TasksApi`: `today`, `cancel`, `parse`, `searchLinks`; every task call accepts `timeZone`.
- `TaskRepository`, `RemoteTaskRepository`, `TaskController`, `TaskControllerState`, `TaskClock`, `TaskTicker`,
  `deviceDueAt`, `isOverdue`, `dayFor`, `TaskStage`, `NoticeAction`, `TaskPrefs`, `StageTime`, `stageTimes`,
  `currentStage`, `stageOf`, `deadlineToken`, `noticeId`, `fnv1a31`, `inQuietHours`, `kNoticeCategory`.
  All of these are implemented.
- Stage schedule: `stageTimes` (device zone, each stage with `last` and `sendAt`), `stageTimesFor(userId:)`,
  `currentStage` and `stageOf` (optional `userId`), `isSendableNow`, `kMaxLeadMinutes`. A date-only task with no
  `dueAt` is scheduled from the device's end of day (another user's: mornings only).
- `RemoteTaskRepository`: device date and zone on every read, `due_at` only for a timed task, `watchOpen()` after
  `refresh()` and writes. `TaskController`: `states` replays the current state; optimistic `complete`, `undo`,
  `refreshDerived` (moves a task that became overdue from `today` to `overdue`; `load` reads every page). `ZoneReporter`: reports a changed zone once, retries after a failure.
- `TaskLabels` gains priority, stage and action strings; `CaptureLabels`, `SettingsLabels`.
- `TaskLabels`: `remindDefault` reads "Use my default"; new strings `noPriority`, `links`, `linkHint`, `removeLink`,
  `todayEmpty`, `laneEmpty`, `anytime`, `dueMarker`, `overdueMarker`, `markerText()`. `CaptureLabels`: `itemTitle`,
  `removeItem`, `noDate`, `searchLink`, `searchLinkHint`, `kindSwitch`. `SettingsLabels`: `invalidTime`, `sameTimes`,
  `invalidLead`.
- Review fixes: `RemoteTaskRepository` lets only the newest re-read emit and reads once for the first listener of
  `watchOpen()`. `TaskController`: only the newest `load` applies and it leaves out tasks completed since it began;
  `undo` waits for an in-flight `complete`; a second `complete(id)` shares the running call; a task that left the
  open stream without this screen completing it triggers one debounced `load` (`reloadDelay`, default 500 ms,
  cancelled by `dispose`) so counts like `doneToday` refresh. Malformed "HH:MM" prefs read as 08:00 / 17:00.
  `make test` runs in `America/Los_Angeles`.
- `sectionTasks(open, nowUtc, ...)`: the day sections derived on the device (overdue; undated; today = every other
  open task whose day is today or earlier; a later day is in none). `TaskController` uses it on load, on each
  open-list emission and in `refreshDerived`; a failed `complete` restores only that task.
- Stage times for a date-only task with a known `dueAt` count the morning slots and the morning close from the
  device-local date of `dueAt` (the dueDate string only when `dueAt` is unknown).
- `CaptureLabels`: `droppedOne`, `droppedMany`, `droppedNotice(n)` (the inline note when the server discarded items) and
  `titleRequired`.
- Removed: `DemoJobsApi.notices()` and `noticesPath` (the old reminder route is gone; `runDueJobs` stays).
  `RemoteTaskRepository` sends `today` only when it has no time zone (the server derives the day from now and `time_zone`).
- `ParseResult.dropped` (default 0): items the model returned that the server discarded (key `dropped`, sent only above zero).
- `TaskCandidate.copyWith` and `EventCandidate.copyWith` (with `clear*` flags) for the capture review.
- New dependency: `crypto` (sha256 for `noticeId`).

## 0.1.0 - unreleased
- `Task` (the `TaskItem` wire shape, exactly its keys), `ChecklistItem`, `TaskLink`, `TaskStatus`, `MirrorStatus`,
  `kRemindNone` (-2) and `kRemindMorningOf` (-1). Due date and time stay `YYYY-MM-DD` / `HH:MM` strings.
- `TaskDraft` (create body, `validate()` for title, title length (`kTaskTitleMaxLength` 255) and time-needs-date) and `TaskPatch` with `Present<T>`:
  an omitted field stays, `Present(null)` clears `notes`, `due_date`, `due_time` or `assigned_user_id`.
- `TaskFilters` (query map), `TaskPage`, `TaskSummary`, `TaskLabels` (English defaults, including a 1 minute reminder).
- `TasksApi(ApiClient, {prefix = '/tasks'})`: list, summary, get, create, update, complete, reopen, delete,
  setChecklistItem; an optional `today` query on the calls that return a task.
- `DemoJobsApi`: `POST /jobs/tick` and `GET /tasks/notices`, fake-mode only, kept apart from `TasksApi`.
- Dropped from the seed: the LLM `parse` call, contact and loan candidate models, per-app exception types
  (the `bond_api` family is used).
