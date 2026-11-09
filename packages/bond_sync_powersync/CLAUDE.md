# bond_sync_powersync
Role: PowerSync connector, store and opener for bond_sync. Flutter package.

## Key files
- `lib/src/connector.dart`: `SyncConnector`. `store.dart`: `PowerSyncSyncStore`. `policy.dart`: `SyncPolicy`.
- `lib/src/store_apply.dart`, `store_resend.dart`: the SQL. `store_open.dart`: `openSyncStore`.
- `lib/src/sync_db.dart`: `SyncDb`, the minimal database seam; `PowerSyncDb` wraps the real database.
- `test/fake_sync_db.dart`: scripted `SyncDb` that records statements.

## Commands
- `make test T=test/store_test.dart`
- `make analyze`

## Rules
- No popups, dialogs or modal sheets; show state inline.
- Logic that needs no database belongs in `bond_sync`; this package holds PowerSync calls and SQL only.
- Table and column names come from the schema, never from a note or the server.
- No codegen; hand-write fromJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
