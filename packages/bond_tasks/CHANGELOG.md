# Changelog

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
