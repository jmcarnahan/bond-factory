# 2026-11-12 Two package splits: bond_push_apple and bond_auth_secure_storage

Status: accepted. Dated, append-only.

## Context

- `bond_tasks_notifications` and `bond_notify_powersync` depended on `bond_push`, which depended on the native `push`
  plugin. An app with push switched off still linked the plugin and had to order its notification delegates around it.
- `bond_signin_ui` depended on `flutter_secure_storage` for one file. On web that pulls a `win32` version that
  conflicts with `file_picker ^8`, which kept such an app off the sign-in widgets.

## Decisions

- **P1** New package `bond_push_apple` (depends on `bond_push` and `push`) holds the four classes that touch the
  plugin: `PushPlugin`, `DefaultPushPlugin`, `PluginPushTokenSource`, `PluginPushTaps`. `bond_push` keeps the
  interfaces and the plugin-free classes and no longer depends on the plugin.
- **P2** New package `bond_auth_secure_storage` (depends on `bond_auth`) holds `SecureRefreshTokenStore`.
  `bond_signin_ui` no longer depends on `flutter_secure_storage`.
- **P3** The old packages do not re-export the moved classes. No other app used them yet, so the import change breaks
  nobody, and a re-export would bring the dependency back.
- **P4** Each new package is registered in the root workspace, in `tool/changed_modules.sh` and in the Flutter lists
  of `make/dart.mk`, and has a consumer check.

## Consequences

- An app imports `package:bond_push_apple/bond_push_apple.dart` for the plugin classes and
  `package:bond_auth_secure_storage/bond_auth_secure_storage.dart` for the keychain store. A web app skips the second.
- An app with push off depends on no native push plugin.
