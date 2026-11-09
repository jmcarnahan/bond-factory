# bond_auth
Role: Auth gateway and token store contracts for the bond app family. Phase 2.

## Commands
- `make test T=test/x_test.dart`
- `make analyze`

## Rules
- No Flutter imports.
- No codegen; hand-write fromJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
