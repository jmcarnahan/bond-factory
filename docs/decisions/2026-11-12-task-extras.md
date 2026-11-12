# 2026-11-12 App columns on tasks, on the server and on the phone

Status: accepted. Dated, append-only. Extends `2026-11-11-links.md` (L5).

## Context

An app with its own task columns (a contact id, a loan id, a reference) could not use the shared task model or the
synced repository without dropping them, and had no place to run its own rule on a write.

## Decisions

- **X1** Dart: `Task.extras` (`Map<String, Object?>`, default empty) holds every key outside the known item keys. It is
  kept by `copyWith` and is NOT written by `Task.toJson`, so the fixtures stay exact. `TaskDraft.extras` and
  `TaskPatch.extras` are merged into the write body after the known keys and never override them.
- **X2** `bond_tasks_powersync`: `tasksTables(extraColumns:, extraIndexes:)` adds the app's columns to the same table
  (a name clash throws). `PowerSyncTaskRepository(extraColumns: {...})` writes only those keys on insert and patch, and
  puts every other column of a row in `Task.extras`.
- **X3** `TaskEnricher` runs inside the same read snapshot, with `extraWatchTables` so a renamed contact re-emits.
  Owner and assignee names are null from the synced store; this is where an app fills them.
- **X4** Python: a `prepare(session, task or None, actor, extras) -> dict` hook on `create`, `update` and
  `sync_routes` runs after the permission check and before anything is written, on REST and sync alike. It sees the
  stored task and the extras, may add derived columns, and may raise `TaskError`. `list_tasks(extra_where=)` filters by
  the app's own columns with the library's ordering and paging. `task_items(labels=)` reads link labels at response time.
- **X5** `TaskTicker.tick()` and `TaskClock.offsetBy(Duration)` let a walk jump a boundary without waiting.

## Consequences

- `prepare` sees the extras, not the other new values of the write. A rule about a field outside the extras (for
  example links) reads the stored task, or the app keeps that field in a column of its own.
- The library does not write the app's stream file: the app adds its columns to the stream query and the upload route.
