# legacy_phone
Role: test-only Dart twin of services/legacy_host: the SDK task store over a phone `tasks` table an app already ships. Never shipped; no app, no main.dart.

## Key files
- `lib/src/legacy_schema.dart`: the app's tables at two stages (`LegacyStage.asShipped`, `widened`), not `tasksTables()`.
- `lib/src/legacy_store.dart`: `legacyTaskRepository`, the adopter recipe built only from the repository's seams (copied into docs/migration/bond_tasks_powersync.md).
- `test/support.dart` (real database, `forEachStage`, `drain`, `RecordingDb`), `test/seed.dart` (rows an old build wrote).
- `test/upload_fixture_test.dart` records/asserts `fixtures/legacy_host/upload_phone_store.json`; services/legacy_host replays it.

## Commands
- `make test` (exports TZ=America/Los_Angeles; every read/write test runs at both stages), `make test T=test/read_test.dart`, `make analyze`
- Regenerate the fixture: `BOND_REGEN_FIXTURES=1 make test T=test/upload_fixture_test.dart`, then `make -C ../../services/legacy_host test T=tests/test_phone_store_upload.py`

## Rules
- Tests are tagged `real_db`: a real local PowerSync database, no service. The first run downloads powersync's native library once.
- A gap is never worked around here: fix the module (opt-in seam) or record the limit in the migration note.
- A real database inside `testWidgets` needs `tester.runAsync` alternating with `pump` (see test/ui_contract_test.dart).
- No app or brand names; the legacy vocabulary is a client and a case. No popups.
