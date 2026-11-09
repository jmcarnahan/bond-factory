# bond_json
Role: Null-safe JSON readers and DateTime parsers shared by every bond package. Phase 1.

## Commands
- `make test T=test/x_test.dart`
- `make analyze`

## Rules
- No Flutter imports.
- No codegen; hand-write fromJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
