# bond_ui
Role: Shared Flutter widgets and design tokens for the bond app family. Phase 1.

## Commands
- `make test T=test/x_test.dart`
- `make analyze`

## Rules
- No popups, dialogs or modal sheets; show state inline.
- No codegen; hand-write fromJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
