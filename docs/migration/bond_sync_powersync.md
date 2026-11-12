# Migrating to bond_sync_powersync

Flutter package (powersync needs Flutter). It holds the PowerSync calls and SQL; the rules live in `bond_sync` (see
`bond_sync.md`). Contracts: `docs/contracts/sync_upload.md`.

## 1. What it replaces

| Piece | Holds |
|---|---|
| `SyncPolicy` | schema, `notUploadedTables`, `createPuts`, `silentWrites`, `rekeyChildren`, `sendCaps`, `endpointOverride`, chunk and give-up limits |
| `syncSupportTables()` | the local-only `sync_rejections` and `sync_meta` tables; add them to the app schema |
| `SyncConnector` | `fetchCredentials` (renew once on 401, `StateError` without an endpoint) and `uploadData` |
| `PowerSyncSyncStore` | `SyncStore` over the database: next CRUD transaction, re-key, raw-table delete, notes, resend |
| `openSyncStore` / `SyncStoreOpener` | open, retry, move aside, start fresh, else `SyncOpenFailure`; `deleteStoreFiles` |
| `changeTargets`, `storeChanges`, `readSnapshot`, `watchSnapshot` | reactive reads (view and raw table both watched) |
| `SyncDb`, `PowerSyncDb` | the minimal database surface; tests fake `SyncDb` |

## 2. The adapter

App S (sbel-crm):
- `lib/sync/core/connector.dart`: delete the class and use `SyncConnector(transport:, clock:, policy:, mapFailure:, onServerNow:)`.
  `SyncPolicy` keeps its shape (`policy.dart` builds it with `schema`, `createPuts`, `silentWrites`, `rekeyChildren`).
- `app/schema.dart`: replace the two hand-written local-only tables with `...syncSupportTables()`. Columns are identical
  (`sync_rejections`: table_name, row_id, action, code, message, payload, created_at, op; `sync_meta`: key, value).
- `core/store_open.dart`: `openSyncStore(policy:, path: syncDbPath(dir, userId, prefix: 'sbel'), names: BondSyncNames(prefix: 'sbel',
  loggerName: 'sbel.sync'))`. The result has `store` (the `SyncStore`) and `powerSync` (the database to `connect`).
- `core/store_reads.dart`: the four helpers take a `SyncDb`. Use `open.db` or `PowerSyncDb(db)`. `rejectionsFor` is `store.rejections()`.

App A (avalon-crm):
- `sync/connector.dart` (776): the generic loop becomes `SyncConnector`; photo upload and the time-table rule stay app-side.
- `sync/sync_database.dart` (474): open ladder, `SyncOpenFailure`, move-aside and `syncDbPath` map to `openSyncStore`,
  `SyncStoreOpener.moveAside`, `deleteStoreFiles`, `BondSyncNames(prefix: 'avalon', loggerName: 'avalon.sync')`.
  `clearStoreOnRemoval`, backup exclusion and the Riverpod wiring stay in the app. `sync/schema.dart` and `photo_files.dart` stay.

## 3. Call-site changes

- Screens read notes through `store.rejections()` / `watchRejections()` and call `store.resend(note)`; the results are the
  same three (`queued`, `rowGone`, `unsupported`).
- Behaviour kept: one transaction for re-keys, raw-table deletes and notes; the raw table is used on purpose so no DELETE is queued.
- Behaviour changed: the dead-row rule is decided before the delete (a failed delete still writes the note and says so).
- Failure map: 5xx is not counted (see `bond_sync.md`); `app/failure_map.dart` shrinks to the app's verdict texts.

## 4. Data

None. The database file name stays through the prefix; `sync_rejections` and `sync_meta` keep their columns.

## 5. Acceptance

1. `make -C packages/bond_sync_powersync test` and `analyze` pass.
2. A real device: sign in, create a row offline, go online, the row uploads and syncs back; the queue is empty.
3. A refused create (bad value) leaves one note next to the row and no optimistic row; resend queues the same write.
4. Kill the app with a damaged database file: the next start moves the files aside (`.bad-<ms>`), starts empty and writes `store_reset`.
5. Expire the sync token: credentials renew once through the session refresh, then the connection resumes.
6. A server `resolved_id` re-keys the row, its child rows and the writes still queued.

## 6. Known gaps (the app keeps these)

- PowerSync on Flutter web needs sqlite wasm and worker assets in `web/`, so the demo exercises `bond_sync` with
  `FakeSyncStore` against the live upload route, and this package is unit tested against a fake `SyncDb`. No test starts a
  sync service. One test (`test/real_database_test.dart`, tag `real_db`) opens a real `PowerSyncDatabase` on a temp file in
  `flutter test` on macOS: powersync 2.6.1's build hook downloads the core library (`libpowersync_core.dylib`, needs network
  once) and no `sqlite3_flutter_libs` setup is needed. It covers the CRUD batch, `uploadData`, queue drain and a recorded
  rejection. Caveat: the hook's `install_name_tool` step fails when the package path is very long (about 190 chars); keep the
  checkout path short. Items 2 to 6 above (real sync service, damaged file, token expiry) still need a phone or simulator.
- A's photos run before the rest of their transaction, so A needs its own ordering around `SyncUploader.uploadNext`;
  decide that before cutover.

## 7. New for the TODO adapters

Three additions, all optional. `bond_tasks_powersync.md` and `bond_notify_powersync.md` use them.

- `waitForUploadDrain(db, {timeout, poll})` returns true once the CRUD queue is empty and false on timeout. Call it
  between the last local write and the sign-out clear. Clearing first loses queued writes, such as a push device delete.
- `package:bond_sync_powersync/testing.dart` exports `FakeSyncDb`, `Stmt` and `CrudRig`, so another package's tests can
  fake the database (`test/fake_sync_db.dart` re-exports it).
- `FakeSyncDb.tables({name: rows})` serves `SELECT .. FROM <name>`. With `applySql: true` and `columns: {...}` it evaluates
  INSERT, UPDATE and DELETE and honours WHERE, ORDER BY and LIMIT in SELECT, so a wrong column or WHERE fails a test. A
  statement shape it cannot read throws. The fake keeps one watch controller per SQL (`watchControllerFor`).
- Add the new tables to the app schema beside `syncSupportTables()`: `tasksTables()`, `noticesTables()`, `pushDevicesTables()`.
