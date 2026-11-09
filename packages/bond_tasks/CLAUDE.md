# bond_tasks
Role: Task models and API client shared by the bond apps. Phase 3.

## Commands
- `make test T=test/x_test.dart`
- `make analyze`

## Rules
- No Flutter imports.
- No codegen; hand-write fromJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
