# Migrating to bond_tasks_powersync

`TaskRepository` over the synced SQLite store (`packages/bond_tasks_powersync`, Flutter: needs `bond_tasks`,
`bond_sync_powersync`, `powersync`). Reads are computed on the device with the server's rules. Writes are local SQL that the
sync upload carries, so the list works offline. Table shapes come from `bond_tasks_py`. Legend: `docs/migration/README.md`.
Order: `todo-checklist.md`. Sync adapter: `bond_sync_powersync.md`.

## 1. What it replaces

An app's own synced task tables and the code that reads them The
controller, the widgets and the alerts coordinator do not change: they take a `TaskRepository`, and this is another one.

## 2. What the app adds

- The table in the schema: `Schema([...tasksTables(), ...syncSupportTables()])`. `tasksTables()` declares every stored column
  as text (`priority`, `remind_minutes_before`, `mirror_enabled` are integers), three indexes and `trackMetadata`. Names
  not stored: `owner_name`, `assignee_name` (null on the `Task`). `overdue` is derived, never stored.
- The stream on the sync service:

```sql
SELECT id, owner_user_id, created_by, assigned_user_id, title, notes, due_date, due_time, priority, due_at,
       status, completed_at, completed_by, checklist, remind_minutes_before,
       mirror_enabled, mirror_status, external_provider, external_event_id, external_account_user_id,
       external_etag, links, source, created_at, updated_at
FROM tasks WHERE owner_user_id = auth.user_id() OR assigned_user_id = auth.user_id()
```

- The upload routes on the server: `sync_routes(Task, ...)` from `bond_tasks_py` handles put, patch, delete and the
  `complete`, `reopen` and `cancel` actions. The sync service needs a `cancel` action route.
- The sign-out order (below).

## 3. Smallest working example

```dart
final repo = PowerSyncTaskRepository(db, userId: userId);   // db is a SyncDb
repo.watchOpen();                 // my open tasks, due soonest first, undated last
await repo.today();               // overdue / today / undated / done today, plus counts
await repo.summary();             // open, overdue, due today, no date
await repo.create(const TaskDraft(title: 'Call back', dueDate: '2026-11-12', dueTime: '15:30'));
await repo.complete(id);
```

`today()` and `summary()` use the device's local day. `list` supports scope, status, owner, assignee, no-date, date range
(by the task's local day) and link filters. Paging is local. `refresh()` does nothing. `taskFromRow(row, nowUtc: now)` decodes
one row. A malformed JSON cell gives an empty list.

## 4. What the device writes

- create: every column, `status` open, `source` (default `manual`), `due_at` the device instant for a timed task and null for
  a date-only task. A date-only task has no `due_at` until the server's answer syncs back, so its `overdue` is date-based
  until then. The id is a client v4 UUID. A supplied id must match `[A-Za-z0-9_-]{1,64}` or `create` throws.
- update: only the patched columns plus `updated_at`. `due_at` is written only for a timed result. Clearing the date also
  nulls `due_time` and `due_at`.
- complete, reopen, cancel: `status`, `completed_at`, `updated_at` and `_metadata` `{"action": ...}` so the upload picks the
  route. Asking for the status a task already has writes nothing. Delete: `DELETE ... WHERE id = ?`.
- The server stays the authority: it replaces `completed_at` and `updated_at` and computes `due_at` of date-only tasks.

## 5. Sign-out

Local writes upload later. Wait for the queue before clearing: `waitForUploadDrain(db)`, then disconnect, then clear the
database. Clearing first loses queued writes. With push: unregister the device, wait for the drain, disconnect, clear.

## 6. What to test

- `make -C packages/bond_tasks_powersync test` (it sets TZ=America/Los_Angeles, and the day-view tests on the shared fixtures
  skip with a message in another zone).
- Use `FakeSyncDb.tables(..., applySql: true, columns: ...)` from `bond_sync_powersync/testing.dart`: a wrong column or WHERE
  fails the test.
- Complete a task offline, then drain: the upload names the `complete` route.
- Not proven here: a real PowerSync service, and how fast a change reaches an open app.
