# bond_json
Role: null-safe JSON readers (`jstr`, `jint`, `jlist`, ...) and UTC timestamp helpers (`jtime`, `jiso`). Pure Dart, no dependencies.

## Key files
- `lib/src/json.dart`: scalar, map and list readers, `JsonShapeError`.
- `lib/src/time.dart`: `jtime`, `jiso`. `lib/src/enums.dart`: `enumByWire`.
- `test/json_test.dart`: every helper.

## Commands
- `make test T=test/json_test.dart`
- `make analyze`

## Rules
- No Flutter, no `dart:io`, no dependencies.
- Missing key returns null and never throws; wrong type throws `JsonShapeError`.
- Times are UTC in and out; naive strings are UTC; ints are not timestamps.
- No codegen; hand-write fromJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
