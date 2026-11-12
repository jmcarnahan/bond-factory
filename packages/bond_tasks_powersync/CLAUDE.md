# bond_tasks_powersync
Role: TaskRepository over the PowerSync SyncDb adapter.

## Key files
- `lib/bond_tasks_powersync.dart` is the barrel; code is in `lib/src/`.
- Tests: `test/barrel_test.dart` references every public name; the rest use `FakeSyncDb.tables(applySql: true)`.

## Commands
- `make test` (the Makefile exports TZ=America/Los_Angeles; the day-view tests skip in other zones)
- `make analyze`

## Notes
- `test/real_database_test.dart` (tag `real_db`) opens a real PowerSync database and needs the native library that
  powersync's build hook downloads once (network on the first run, then cached in `build/`). Missing, the test
  fails at `db.initialize()` with a native-library load / "Failed to load dynamic library" style error: run once online.

## Rules
- Public names and signatures are final. Every write's SQL and parameters are asserted in tests.
- No popups, dialogs, sheets or snack bars. No raw colours (use BondTokens). No intl, riverpod, go_router.
- Every user-visible string comes from a labels object with English defaults.
- No codegen; hand-write fromJson / toJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
