# bond_tasks

Task models and REST client shared by the bond apps. Pure Dart (`bond_json`, `bond_api`), no Flutter.

```dart
final api = TasksApi(apiClient); // prefix '/tasks'
final page = await api.list(const TaskFilters(scope: 'mine', status: 'open', today: '2026-03-12'));
final task = await api.create(const TaskDraft(title: 'Send the estimate', dueDate: '2026-03-12', dueTime: '09:30'));
await api.update(task.id, const TaskPatch(dueDate: Present(null))); // clears the date; omitted fields stay
```

- `Task` reads and writes exactly the `TaskItem` keys (`fixtures/tasks/task.json`).
- Due date and time are `YYYY-MM-DD` and `HH:MM` strings (local wall clock, never UTC).
- `remind_minutes_before`: `kRemindNone` (-2), `kRemindMorningOf` (-1), or minutes before.
- `DemoJobsApi` is for the fake-mode example only.
