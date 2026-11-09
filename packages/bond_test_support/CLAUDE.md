# bond_test_support
Role: shared widget-test helpers: overlay check, screen sizes, `FakeCall`, `CannedHttpClient`, waits, `pumpApp`. Used from other packages' `dev_dependencies`.

## Key files
- `lib/src/overlays.dart`: `expectNoOverlays`; matches type-name fragments, never spells overlay widgets (the popup gate scans `lib/`).
- `lib/src/waits.dart`: `pumpUntil`, `pollUntil`, `Emissions`. `lib/src/canned_http.dart`, `fake_call.dart`, `screen.dart`, `pump_app.dart`.

## Commands
- `make test T=test/support_test.dart`
- `make analyze`

## Rules
- No popup widgets in `lib/`, not even in tests' helpers; self-tests that open one live in `test/`.
- Every wait fails with a readable message at its cap; never lengthen a cap to make a test pass.
- No app-specific fakes (no api, auth or db doubles of one app).
- No codegen; hand-write fromJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
