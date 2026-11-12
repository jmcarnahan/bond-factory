# bond_tasks_notifications
Role: Flutter local alerts for tasks: AlertPlugin seam, scheduling, action handler, coordinator.

## Key files
- `lib/bond_tasks_notifications.dart` is the barrel; code is in `lib/src/`.
- Tests: `test/barrel_test.dart` references every public name.

## Commands
- `make test T=test/barrel_test.dart`
- `make analyze`

## Rules
- Public names and signatures are final; unimplemented bodies throw `UnimplementedError('<name> is not implemented yet')`.
- No popups, dialogs, sheets or snack bars. No raw colours (use BondTokens). No intl, riverpod, go_router.
- Every user-visible string comes from a labels object with English defaults.
- No codegen; hand-write fromJson / toJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
