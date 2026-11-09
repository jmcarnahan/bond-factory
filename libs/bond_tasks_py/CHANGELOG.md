# Changelog

## 0.1.0 - unreleased
- `TasksMixin` (table `tasks`), `TaskStatus`, `MirrorStatus`, `TASK_COLUMNS`.
- Service: `create`, `update`, `complete`, `reopen`, `cancel`, `delete`, `get`, `set_checklist_item`, `list_tasks`,
  `summary`, `TaskFilters`, `TaskCreate`, `TaskUpdate`, `TaskError` with coded refusals.
- Reminders: `compute_remind_at`, `schedule_reminder`, `cancel_reminder`, `fire_reminder`, Protocol `Scheduler`.
- Mirror: `sync_mirror`, `remove_event`, `mark_mirror`, Protocols `CalendarMirror`, `MirrorProviders`, `MirrorDraft`.
- Wire shape: `task_item`, `task_items`, `ITEM_KEYS`. Sync: `sync_routes`, `verdict_for`.
