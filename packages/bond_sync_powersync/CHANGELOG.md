# Changelog

## Unreleased
- `store_open.dart` no longer imports `dart:io`: the file moves and deletes sit behind a conditional import (`store_files_io.dart`; on the web `store_files_stub.dart`, where moving aside moves nothing and deleting does nothing, silently). Public API unchanged. `make -C packages/bond_sync_powersync web-compile` (root `make web-compile-sync`, which `make test-flutter` runs) fails if any file but `store_files_io.dart` imports `dart:io`, and compiles the opener to JavaScript. Nothing was run in a browser.
- `FakeSyncDb` with `applySql: true` also runs `SELECT COUNT(*) [AS n] FROM t [WHERE ...]` (one row, the count of the
  matches) and `LIMIT n OFFSET m`. Additive; every statement it ran before reads the same.
- `waitForUploadDrain(db, {timeout, poll})`: true once the CRUD queue is empty, false on timeout. Call it between the last
  local write and a sign-out clear.
- `FakeSyncDb.tables(..., applySql: true, columns: {...})` evaluates SQL against `tables`: INSERT (also OR REPLACE),
  UPDATE and DELETE change the rows and pulse `changes`; SELECT honours WHERE, ORDER BY and LIMIT; a column not
  in `columns` throws. Off by default; `refineRows` still wins. A statement shape it cannot read throws.
- `package:bond_sync_powersync/testing.dart` exports `FakeSyncDb`, `Stmt`, `CrudRig` for other packages' tests
  (`test/fake_sync_db.dart` re-exports it).
- The fake gains a watch controller per SQL (`watchControllerFor`; `watchController` still reaches every
  watcher), `emitOnListen`, and `FakeSyncDb.tables({name: rows})` (reads `SELECT .. FROM <name>`; `refineRows`
  narrows them).

## 0.1.0 - unreleased
First API. Flutter package (powersync needs Flutter). Imports `bond_sync`; the core imports nothing from here.

- `SyncPolicy({schema, notUploadedTables, createPuts, silentWrites, rekeyChildren, sendCaps, endpointOverride,
  chunkSize, chunkBytes, transient*})`; getters `schemaTables`, `sendableTables`, `rules`, `limits`.
- `syncSupportTables()`: the two local-only tables the adapter keeps (`sync_rejections`, `sync_meta`).
  Add them to the app schema.
- `SyncConnector({transport, mapFailure, clock, policy, onServerNow})` extends `PowerSyncBackendConnector`.
  `fetchCredentials`: on `unauthorized`, `refreshSession() == renewed`, then ask once more; `StateError`
  when no endpoint is known. `uploadData` runs one `SyncUploader.uploadNext`; any retry reaches the SDK as a
  plain `Exception`, a permanent outcome never throws. `uploadWith(SyncStore)` is the same without a database.
- `PowerSyncSyncStore implements SyncStore` (one transaction for re-keys, raw-table deletes and notes).
- `openSyncStore(...)` / `SyncStoreOpener`: open, retry the same files, move them aside (never delete),
  start fresh, else `SyncOpenFailure`. `deleteStoreFiles`. `BondSyncNames` and `syncDbPath` are re-exported.
- Reactive reads lifted from the seed: `changeTargets`, `storeChanges`, `readSnapshot`, `watchSnapshot`
  (view and raw table both watched, latest read wins), now over `SyncDb`.
- `SyncDb` / `SyncSql` / `PowerSyncDb`: the minimal database surface the adapter uses; tests fake `SyncDb`.

### Differences from the seed
- The connector's upload loop is `SyncUploader` in bond_sync; only the database calls are here.
- A refused create and its later writes: the planner marks the row dead when the create is refused; the seed
  marked it only after the raw delete succeeded. A failed delete still writes the note and says so.
- The store opener logs under `BondSyncNames.loggerName`; the database file prefix is an argument.

### Limit
PowerSync on Flutter web needs sqlite wasm and worker assets in `web/`; this package is unit tested against a
fake `SyncDb` only. No test starts a database or a sync service.
