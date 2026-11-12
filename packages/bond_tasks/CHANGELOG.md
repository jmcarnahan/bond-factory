# Changelog

## 0.2.0 - unreleased
- `Task.priority` (`TaskPriority`) and `Task.dueAt` (keys `priority`, `due_at`, right after `due_time`);
  `TaskDraft` and `TaskPatch` gain `priority`, `dueAt`, `timeZone`; `TaskFilters.timeZone`; `kRemindUseDefault` (-3);
  `Task.copyWith`.
- `TaskToday`, `TaskTodayCounts`; `ParseResult`, `CaptureItem` (`TaskCandidate`, `EventCandidate`), `LinkCandidate`,
  `LinkOption`; `TaskSettings`, `TaskSettingsPatch`, `TaskSettingsApi`; `LinkSearch`; `TimeZoneSource`, `ZoneReporter`.
- `TasksApi`: `today`, `cancel`, `parse`, `searchLinks`; every task call accepts `timeZone`.
- `TaskRepository`, `RemoteTaskRepository`, `TaskController`, `TaskControllerState`, `TaskClock`, `TaskTicker`,
  `deviceDueAt`, `isOverdue`, `dayFor`, `TaskStage`, `NoticeAction`, `TaskPrefs`, `StageTime`, `stageTimes`,
  `currentStage`, `stageOf`, `deadlineToken`, `noticeId`, `fnv1a31`, `inQuietHours`, `kNoticeCategory`.
  `deviceDueAt`, `isOverdue`, `dayFor`, `deadlineToken`, `inQuietHours`, `TaskTicker` and `TaskClock` are real;
  `stageTimes`, `currentStage`, `stageOf`, `RemoteTaskRepository`, `TaskController` and `ZoneReporter` throw
  `UnimplementedError` until they are built.
- `TaskLabels` gains priority, stage and action strings; `CaptureLabels`, `SettingsLabels`.
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
