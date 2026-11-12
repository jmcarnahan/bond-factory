# bond_push
Role: Flutter push seam: token source, device registration, registrar and taps (iOS only).

## Key files
- `lib/bond_push.dart` is the barrel; code is in `lib/src/`.
- Tests: `test/barrel_test.dart` references every public name; `test/push_test.dart` covers source, taps, registrar.

## Commands
- `make test T=test/barrel_test.dart`
- `make analyze`

## Rules
- Public names and signatures are final. The `push` plugin is reached only through `src/push_plugin.dart`; tests import the `PushPlugin` seam from `lib/testing.dart`, adopters never from `src/`.
- No popups, dialogs, sheets or snack bars. No raw colours (use BondTokens). No intl, riverpod, go_router.
- Every user-visible string comes from a labels object with English defaults.
- No codegen; hand-write fromJson / toJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
