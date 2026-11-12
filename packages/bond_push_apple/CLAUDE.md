# bond_push_apple
Role: the pub.dev `push` plugin behind the bond_push seams: Apple token source and taps (iOS only).

## Key files
- `lib/bond_push_apple.dart` is the barrel; code is in `lib/src/`.
- `lib/src/push_plugin.dart` PushPlugin seam + DefaultPushPlugin (the only file that imports `push`).
- `lib/src/plugin_push_token_source.dart` PluginPushTokenSource; `plugin_push_taps.dart` PluginPushTaps.
- Tests: `test/barrel_test.dart` names; `test/push_apple_test.dart` source, taps, registrar over a fake plugin.

## Commands
- `make test T=test/barrel_test.dart`
- `make analyze`

## Rules
- Depends on bond_push and `push`. An app with push off must not depend on this package.
- Tests use the `PushPlugin` seam; never a platform channel.
- No popups, dialogs, sheets or snack bars. No intl, riverpod, go_router. No codegen.
- Barrel + CHANGELOG.md updated on every public API change. 300-line soft cap per source file.
