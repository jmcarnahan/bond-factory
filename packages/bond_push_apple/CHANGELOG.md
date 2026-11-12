# Changelog

## 0.1.0 - unreleased
- New package, split out of `bond_push`: `PushPlugin`, `DefaultPushPlugin`, `PluginPushTokenSource`, `PluginPushTaps`.
  Import them from `package:bond_push_apple/bond_push_apple.dart`. `bond_push` no longer depends on the `push` plugin
  and does not re-export these names.
- `PushPlugin` is now exported from the barrel (it was in `package:bond_push/testing.dart`, which is gone).
