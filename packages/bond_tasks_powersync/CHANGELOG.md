# Changelog

## Unreleased
Phase 2 (same opt-in rule: nothing here changes a default).
- `PowerSyncTaskSettingsStore` (a `TaskSettingsStore`), `taskSettingsTables({table, rename})`, `kTaskSettingsTable`
  (`task_user_settings`), `kTaskSettingsColumns` (`time_zone`, `start_of_day`, `end_of_day` text; `lead_minutes` integer).
  One row per user, id = the user id. `get`, `watch()` (re-emits after a local write and after a row arrives by sync), `update`.
  Read: a NULL cell or no row gives the `defaults:` value; `overridden` is the wire names whose cell is not NULL (empty with no
  row); `warnings` is always empty (the server's warnings do not travel over sync). Update: no row is
  `INSERT INTO <t> (id, <only the columns set or reset>) VALUES (...)` (a queued put); a row is `UPDATE <t> SET <only those> WHERE id = ?`
  (a queued patch); `reset` writes NULL and wins over a value; an empty patch writes nothing; `start_of_day` / `end_of_day`
  must be `HH:MM` and `lead_minutes` 0..10080 (`ArgumentError`, nothing written; `update` fails as a Future; the zone is not
  checked locally); returns the settings read back. `rename` maps a
  wire name to the local column (SQL and queued keys use the local names); table and column names are checked like
  `TaskTableShape.rename` (`ArgumentError`). A `ZoneReporter` over the store writes the device zone once.
- `listWhere` / `watchWhere` take `mine` (default false): adds `(owner_user_id = ? OR assigned_user_id = ?)` in SQL, after the
  equals conditions and before the status; an EMPTY `equals` map is now accepted (it used to throw `ArgumentError`; no WHERE
  when nothing filters). Mine: `watchOpen` or `listWhere({}, mine: true)`; a linked record: `listWhere({'client_ref': id})`;
  everyone: `listWhere({})`. A `status` other than `open`, `done`, `cancelled` does not filter, so cancelled rows show only then.
- Pinned (test only): ticking a checklist item through `update` stores and queues its `done_at` (no `done` key); unticking with
  `copyWith(clearDone: true)` stores and queues `done: false` for that item only; a later edit re-sends it with no `done`.
Opt-in seams for an app whose phone database already exists (a local `tasks` table of its own). With none of the new
arguments given, every SQL string, parameter list and result is as before; the two lines under "Changed by default" are the only
exceptions.
- `TaskTableShape({absent, rename, dueOrder})` and `TaskDueOrder {dueAt, dateThenTime}`; `PowerSyncTaskRepository(shape:)`
  (default: the module's table). `absent` lists module columns (`kTaskColumns`) the local table lacks: SQL never names them, a draft
  or patch value for one is dropped silently, a read gives null. `rename` maps a module column to its local column (the flag
  `mirror_enabled` to `sync_to_calendar`, say); a renamed column is read by its module name and never lands in `Task.extras`; a
  NULL flag reads as on. `dueOrder` defaults to `dateThenTime` when `due_at` is absent, else `dueAt`: `dateThenTime` is
  `ORDER BY due_date IS NULL, due_date, due_time IS NULL, due_time, created_at DESC, id` (used by `watchOpen`, `today`,
  `summary`, `list` and the new reads); `dueAt` is today's order. `check(extraColumns)` (run by the constructor) throws
  `ArgumentError` for an unknown module column, an absent column the rules need (`owner_user_id`, `assigned_user_id`, `title`,
  `status`, `due_date`, `due_time`, `completed_at`, `created_at`, `updated_at`), a renamed column also absent, an unsafe or
  reserved or duplicate local name, a local name that is another module column or an extra column, and `dueOrder: dueAt` with
  `due_at` absent. `taskFromRow(..., shape:)`: the `mirrorStatusFor` hook still gets the row as stored (local names).
- `PowerSyncTaskRepository(writeCompletedBy: true)`: complete writes `completed_by` = the user, reopen and cancel write NULL (skipped
  when the column is absent). Default false: the status statement is unchanged.
- `PowerSyncTaskRepository(mirrorStatusOnWrite:)`, `MirrorStatusOnWrite` (`String? Function(SyncRow after, SyncRow? before)`):
  called on create, update (only when it writes something), complete, reopen and cancel; `after` is the row as it will be stored
  (`before` merged with the written values, local names, `id` included). A non-null result is written to `mirror_status` in the same
  statement (ignored when that column is absent); null keeps today's behaviour (create writes `pending`, the others do not touch
  it). A throw fails the write and rolls the transaction back. Default null.
- `PowerSyncTaskRepository(prepare:)`, `TaskPrepare`, and `afterWrite:`, `TaskAfterWrite`; `TaskWrite {kind, id, before, values}`,
  `TaskWriteKind {create, update, complete, reopen, cancel, delete}`. One write transaction runs: read `before` -> build `values`
  (local column names, absent columns dropped) -> `prepare` (create and update only) -> `mirrorStatusOnWrite` -> the statement ->
  `afterWrite` -> read back the enriched result. `prepare` returns the values to write: it may change values and add keys, but an
  added key must be in `extraColumns`, already in `values`, or a declared local column other than `id`, else `ArgumentError` and
  nothing is written; it may read any table through `tx`; for an update it runs even when the patch produced no column and an empty
  result writes nothing (no `afterWrite`). On create `values` holds `updated_at` already; on update the module adds `updated_at`
  after `prepare`. `afterWrite` runs after every statement that ran (delete too, with empty `values`; `before` is the stored row,
  null on create or for a missing row) and not when a status action is already satisfied or an update writes nothing. Delete reads
  the row first only when `afterWrite` is set. The upload entry carries exactly the local column names written. Defaults null.
- New reads (all enriched by `enricher`; the watches listen to the tasks table and `extraWatchTables`): `getTask(id)`,
  `watchTask(id)` (null when missing); `listWhere(equals, {status, limit, offset})` and `watchWhere(...)`: keys are module columns
  (mapped through the shape) or `extraColumns`, a null value is `IS NULL`, a bool is 1 or 0, `status` of `open`, `done` or
  `cancelled` filters (another value does not), NOT filtered by owner, `limit` 25 and `offset` 0 by default, `total` is the full count in
  the same snapshot; an empty map, an unknown key, `id` or an absent column throws `ArgumentError` before any SQL.
  SQL: `SELECT * FROM tasks WHERE k1 = ? AND k2 IS NULL [AND status = ?] <order> LIMIT ? OFFSET ?` and
  `SELECT COUNT(*) AS n FROM tasks WHERE ...`. `watchList(TaskFilters)`: `list` as a live snapshot.
- `patchColumns`, `insertTask`, `updateColumns` and `setStatus` take an optional `shape` (and `setStatus` `writeCompletedBy`, `userId`).
- Changed by default (tolerant reader, only how malformed or blank input reads): a blank string (empty or only spaces) in
  `assigned_user_id`, `due_date` or `due_time`, and the empty string `''` in `notes` (spaces-only notes are kept), now decode as null
  (they were kept as written). The derived due instant (a timed row with no `due_at` gets `deviceDueAt(due_date, due_time)`)
  applies only under a shape that has `absent` or `rename` entries or `dateThenTime`; with the default shape a missing `due_at`
  still reads as null (existing tests pin that).
- Guards on the hooks and inputs: a `prepare` for a create must still return every required column (`owner_user_id`,
  `assigned_user_id`, `title`, `status`, `due_date`, `due_time`, `completed_at`, `created_at`, `updated_at`, by local name), so `{}`
  cannot insert a bare row; a `prepare` for an update may not add or change `status`, `completed_at` or `completed_by` (use
  complete, reopen or cancel); both throw `ArgumentError` and nothing is written. The repository copies `shape`,
  `extraColumns` and `extraWatchTables` at construction (changing the caller's collections later changes nothing).
  Names SQLite refuses as an unquoted column name (54, the list `kSqliteKeywords` in `extra_names.dart`, found by running each through
  CREATE TABLE, INSERT, UPDATE, SELECT ... ORDER BY and CREATE INDEX: `order`, `index`, `group`, `case`, `select`, `where` ...) are
  rejected as a rename target and, new by default, as an `extraColumns` / `tasksTables(extraColumns:)` name (`ArgumentError`).
  Those names never worked, because the SQL is unquoted: the check turns a runtime SQL error into an `ArgumentError` at
  construction. No working name is refused (`key`, `end`, `by`, `offset`, `column`, `like` stay allowed). `watchWhere` throws a
  negative `limit` or `offset` at call time; `listWhere` fails with the same `ArgumentError`.
- `afterWrite` also fires for a delete of a row that does not exist, with `before == null`.

## 0.1.0 - unreleased
- `PowerSyncTaskRepository(mirrorStatusFor:)` and `MirrorStatusFor` (`String? Function(SyncRow row)`): the app says which mirror state an offline row shows; null keeps the stored value; default null changes nothing. An unknown string shows as `pending`; a hook that throws keeps the stored value for that row and the list still shows. `taskFromRow` takes the same hook.
- `tasksTables({extraColumns, extraIndexes})` (an `ArgumentError` on a name clash, an unsafe name or an index name that repeats a built-in one; names match `^[a-z_][a-z0-9_]*$`, checked case-insensitively against built-in columns, `id`, `_metadata` and `TaskItem` keys; the repository constructor runs the same check); `PowerSyncTaskRepository(extraColumns:,
  enricher:, extraWatchTables:)`; `TaskEnricher`. Inserts and patches write only the declared extras; `taskFromRow` puts every
  column outside the built-in set into `Task.extras`. A bool extra reads back as `int` (stored 0/1). An enricher that returns another number of tasks throws `StateError`.
Note
- The `remind_at` and `reminded_at` columns are not part of the tasks table or stream query (removed with the queued reminder).

- First API. `tasksTables()` (with `kTaskColumns`), `taskFromRow` and `PowerSyncTaskRepository` are implemented: day view and
  counts computed on the device, writes as local SQL (status changes carry a `_metadata` action).
