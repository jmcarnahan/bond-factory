# bond_push
Role: push seams: token source, device registration, registrar and taps (iOS only). No plugin: the `push` plugin lives in bond_push_apple.

## Key files
- `lib/bond_push.dart` is the barrel; code is in `lib/src/`.
- Tests: `test/barrel_test.dart` references every public name; `test/push_test.dart` covers the registrar over a fake source.

## Commands
- `make test T=test/barrel_test.dart`
- `make analyze`

## Rules
- Public names and signatures are final. No dependency on the `push` plugin (it is in bond_push_apple); the lib imports no Flutter. Adopters never import from `src/`.
- No popups, dialogs, sheets or snack bars. No raw colours (use BondTokens). No intl, riverpod, go_router.
- Every user-visible string comes from a labels object with English defaults.
- No codegen; hand-write fromJson / toJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
