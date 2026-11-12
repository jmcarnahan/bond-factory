# Changelog

## 0.1.0 - unreleased
- First API: `PushTokenSource`, `PushToken`, `PushDevices` / `PushDevicesApi`, `PushRegistrar`, `PushTap`, `PushTaps`.
- `PluginPushTokenSource` and `PluginPushTaps` over the `push` plugin, through a small `PushPlugin` seam (optional
  `plugin:` argument, for tests). Taps carry no action: the plugin does not report the pressed button.
- `package:bond_push/testing.dart` exports the `PushPlugin` seam for tests.
- `PushRegistrar` also retries a register call that throws, `start()` while started is a no-op, and `unregister()`
  waits for a register in flight and can be followed by a new `start()`.
- `PushRegistrar` retries a late token (`retries` 5, `retryDelay` 2 s, injectable `delay`), re-registers on refresh,
  reports failures on `errors`, and never asks for permission.
