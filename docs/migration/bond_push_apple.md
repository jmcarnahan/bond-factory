# Migrating to bond_push_apple

The pub.dev `push` plugin behind the `bond_push` seams (`packages/bond_push_apple`). iOS only. Split out of `bond_push` on
2026-11-12 so an app with push off links no plugin and needs no notification-delegate ordering. Main notes:
`bond_push.md`. Legend: `docs/migration/README.md`.

## 1. What it holds

`PluginPushTokenSource`, `PluginPushTaps`, `PushPlugin`, `DefaultPushPlugin`. Depends on `bond_push` and `push`.

## 2. What the app does

- Push on: add `bond_push_apple` to the pubspec (git ref, `path: packages/bond_push_apple`) and change the imports:

| Names | Old import | New import |
|---|---|---|
| `PluginPushTokenSource`, `PluginPushTaps` | `package:bond_push/bond_push.dart` | `package:bond_push_apple/bond_push_apple.dart` |
| `PushPlugin` (tests) | `package:bond_push/testing.dart` | `package:bond_push_apple/bond_push_apple.dart` |

  Keep the `bond_push` import for `PushRegistrar`, `PushDevicesApi`, `PushTap` and the rest.
- Push off: do nothing. Pass `NoPushTokenSource` / `NoPushTaps`, or no push at all, to the coordinator. The plugin is not
  linked. Do not add this package.

## 3. What to test

`make -C packages/bond_push_apple test` and `analyze`. The proof that the plugin is gone from the other packages:
`bond_tasks_notifications` and `bond_notify_powersync` have no `push` in their dependency closure.
