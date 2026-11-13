# bond_tasks_powersync
Role: TaskRepository over the PowerSync SyncDb adapter.

## Key files
- `lib/bond_tasks_powersync.dart` is the barrel; code is in `lib/src/`.
- Reads `powersync_task_repository.dart`; a write runs in `task_write_flow.dart` (prepare, mirror, statement, afterWrite) over
  `task_writes.dart`; `task_queries.dart` SELECT text; `task_hooks.dart`; `task_table_shape.dart` (an existing table's shape).
- Tests: `barrel_test.dart` + `barrel_shape_test.dart` reference every public name; the rest use `FakeSyncDb.tables(applySql: true)`;
  `shape_*_test.dart` use the legacy table of `shape_support.dart`.

## Commands
- `make test` (the Makefile exports TZ=America/Los_Angeles; the day-view tests skip in other zones)
- `make analyze`

## Notes
- `real_database_test.dart` and `shape_real_database_test.dart` (tag `real_db`) open a real PowerSync database: they need the native
  library powersync's build hook downloads once (network on the first run, then cached in `build/`); missing, `db.initialize()` fails.

## Rules
- Public names and signatures are final; a fix is an opt-in seam whose default keeps today's SQL (asserted in tests).
- No popups, dialogs, sheets or snack bars. No raw colours (use BondTokens). No intl, riverpod, go_router.
- Every user-visible string comes from a labels object with English defaults.
- No codegen; hand-write fromJson / toJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
