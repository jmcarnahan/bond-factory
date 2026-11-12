# Changelog

## 0.1.0 - unreleased
- `PowerSyncTaskRepository(mirrorStatusFor:)` and `MirrorStatusFor` (`String? Function(SyncRow row)`): the app says which mirror state an offline row shows; null keeps the stored value; default null changes nothing. An unknown string shows as `pending`; a hook that throws keeps the stored value for that row and the list still shows. `taskFromRow` takes the same hook.
- `tasksTables({extraColumns, extraIndexes})` (an `ArgumentError` on a name clash, an unsafe name or an index name that repeats a built-in one; names match `^[a-z_][a-z0-9_]*$`, checked case-insensitively against built-in columns, `id`, `_metadata` and `TaskItem` keys; the repository constructor runs the same check); `PowerSyncTaskRepository(extraColumns:,
  enricher:, extraWatchTables:)`; `TaskEnricher`. Inserts and patches write only the declared extras; `taskFromRow` puts every
  column outside the built-in set into `Task.extras`. A bool extra reads back as `int` (stored 0/1). An enricher that returns another number of tasks throws `StateError`.
Note
- The `remind_at` and `reminded_at` columns are not part of the tasks table or stream query (removed with the queued reminder).

- First API. `tasksTables()` (with `kTaskColumns`), `taskFromRow` and `PowerSyncTaskRepository` are implemented: day view and
  counts computed on the device, writes as local SQL (status changes carry a `_metadata` action).
