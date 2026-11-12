# bond_tasks_powersync

`TaskRepository` over the synced SQLite store (`bond_sync_powersync`). Reads are computed on the device with the
server's rules; writes are local SQL that the sync upload carries, so the list works offline.

## Add the table

```dart
final schema = Schema([...tasksTables(), ...syncSupportTables()]);
```

`tasksTables()` declares every stored task column (text, with `priority`, `remind_minutes_before` and
`mirror_enabled` as integers), three indexes and `trackMetadata`. `owner_name` and `assignee_name` are not stored
(null on the `Task`); `overdue` is derived, never stored.

## Stream query (on the app's sync service)

```sql
SELECT id, owner_user_id, created_by, assigned_user_id, title, notes, due_date, due_time, priority, due_at,
       status, completed_at, completed_by, checklist, remind_minutes_before,
       mirror_enabled, mirror_status, external_provider, external_event_id, external_account_user_id,
       external_etag, links, source, created_at, updated_at
FROM tasks WHERE owner_user_id = auth.user_id() OR assigned_user_id = auth.user_id()
```

Booleans arrive as 0/1, `checklist` and `links` as JSON text, datetimes as ISO text (no Z means UTC).

## What the device writes

- create: every column; `status` open, `source` (default `manual`), `due_at` the device instant for a timed task,
  null for a date-only task. A date-only task therefore has no `due_at` until the server's answer syncs back, and
  its `overdue` flag is date-based until then. The id is a client v4 UUID; a supplied id must match the sync id
  rule `[A-Za-z0-9_-]{1,64}` or `create` throws.
- update: only the patched columns plus `updated_at`. `due_at` is written only for a timed result (date and time both
  set); a date-only result writes null (the server computes it). Clearing the date also nulls `due_time` and `due_at`.
- complete / reopen / cancel: `status`, `completed_at`, `updated_at` and `_metadata` = `{"action": "complete" |
  "reopen" | "cancel"}`, so the upload picks the route. The sync service needs a `cancel` action route.
- Asking for the status a task already has (complete a done task, ...) writes nothing.
- delete: `DELETE ... WHERE id = ?`.

The server stays the authority: it replaces `completed_at` and `updated_at` and computes `due_at` of date-only tasks.

## Use

```dart
final repo = PowerSyncTaskRepository(db, userId: userId); // db is a SyncDb
repo.watchOpen();            // my open tasks, due soonest first, undated last
await repo.today();          // overdue / today / undated / done today, plus counts
await repo.summary();        // open, overdue, due today, no date
await repo.complete(id);
```

`today()` and `summary()` use the device's local day. `list` supports scope, status, owner, assignee, no-date, date
range (by the task's local day) and link filters; paging is local. `refresh()` does nothing.

`taskFromRow(row, nowUtc: now)` decodes one row; a malformed JSON cell gives an empty list, never a throw.

## Your own columns, names and tables
```dart
tasksTables(extraColumns: [Column.text('loan_id')], extraIndexes: [Index('loan', [IndexedColumn('loan_id')])]);
PowerSyncTaskRepository(db, userId: id, extraColumns: {'loan_id'}, enricher: fillNames, extraWatchTables: ['people']);
```
- A column that clashes with a built-in name throws `ArgumentError`.
- Column names must match `^[a-z_][a-z0-9_]*$` and must not be a built-in column, `id`, `_metadata` or a `TaskItem` key (any case); an extra index name must not repeat a built-in one. Both `tasksTables` and the repository constructor throw `ArgumentError`.
- A bool extra is stored as 0/1 and reads back as `int`.
- Inserts and patches write only the names in `extraColumns`, taken from `TaskDraft.extras` / `TaskPatch.extras`; other keys are ignored.
- `mirrorStatusFor: (SyncRow row) => 'mirrored'` (or null for "keep the stored value") shows the right mirror state for a row that has not synced yet. It only changes what is read; nothing is written. An unknown string shows as `pending`. A hook that throws keeps the stored value for that row, and the list still shows. Default null: the stored `mirror_status` shows. `taskFromRow` takes the same `mirrorStatusFor:`.
- `taskFromRow` puts every column outside the built-in set into `Task.extras`.
- `TaskEnricher = Future<List<Task>> Function(SyncSql sql, List<Task> tasks)` runs inside the same read snapshot, must return the same number of tasks in the same order (else `StateError`), (and the write
  transaction for a write's result). Use `task.copyWith(ownerName:, assigneeName:)`. A change in a table named in
  `extraWatchTables` re-runs `watchOpen`.

## Sign-out

Local writes upload later. Before signing out, wait for the queue (`waitForUploadDrain(db)` from
`bond_sync_powersync`), then disconnect and clear the database; clearing first loses queued writes. With the push
registration (`SyncPushDevices.unregister`) the order is: unregister, wait for the drain, disconnect, clear.

## Wiring with the alerts coordinator

```dart
final tasks = PowerSyncTaskRepository(db, userId: userId);
final feed = WatchNoticeFeed(db, userId: userId);          // bond_notify_powersync
final devices = SyncPushDevices(db, userId: userId);       // bond_notify_powersync
final alerts = TaskAlertsCoordinator(/* tasks, feed, alert plugin, registrar built on devices */);
alerts.start();
```

See `bond_tasks_notifications` for the coordinator's parameters.

## Tests

`make test` (sets TZ=America/Los_Angeles). The day-view tests on the shared fixtures skip with a message in another zone.
`FakeSyncDb.tables(..., applySql: true, columns: ...)` evaluates the SQL, so a wrong column or WHERE fails a test.
