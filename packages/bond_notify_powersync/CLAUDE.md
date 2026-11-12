# bond_notify_powersync
Role: NoticeFeed and PushDevices over the PowerSync SyncDb adapter.

## Key files
- `lib/bond_notify_powersync.dart` is the barrel; code is in `lib/src/`.
- Tests: `test/barrel_test.dart` references every public name; the rest use `FakeSyncDb.tables(applySql: true)`.

## Commands
- `make test` (exports TZ=America/Los_Angeles)
- `make analyze`

## Notes
- `test/real_database_test.dart` (tag `real_db`) opens a real PowerSync database and needs the native library that
  powersync's build hook downloads once (network on the first run, then cached in `build/`). Missing, the test
  fails at `db.initialize()` with a native-library load / "Failed to load dynamic library" style error: run once online.
- Sign-out order: `SyncPushDevices.unregister`, then `waitForUploadDrain(db)`, then disconnect and clear the database;
  clearing first loses the queued DELETE.

## Rules
- Public names and signatures are final. Every write's SQL and parameters are asserted in tests.
- No popups, dialogs, sheets or snack bars. No raw colours (use BondTokens). No intl, riverpod, go_router.
- No codegen; hand-write fromJson / toJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
