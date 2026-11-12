# Migrating to bond_push

Apple push for the apps: the device token, registering it with the service, and taps on a push. iOS only. Android is not
supported. Two packages: `packages/bond_push` holds the seams and plain classes and has no plugin; `packages/bond_push_apple`
(`bond_push_apple.md`) holds the pub.dev `push` plugin classes. No Firebase. Server half:
`bond_push_py.md`. Wire: `docs/contracts/notices.md`. Legend: `docs/migration/README.md`. Order: `todo-checklist.md`.

## Moved names (split of 2026-11-12)

Old import, new import. No re-export is kept in `bond_push`.

| Names | Was | Now |
|---|---|---|
| `PluginPushTokenSource`, `PluginPushTaps` | `package:bond_push/bond_push.dart` | `package:bond_push_apple/bond_push_apple.dart` |
| `PushPlugin` | `package:bond_push/testing.dart` | `package:bond_push_apple/bond_push_apple.dart` |
| `DefaultPushPlugin` | not exported | `package:bond_push_apple/bond_push_apple.dart` |

Pubspec: add `bond_push_apple` (git ref, `path: packages/bond_push_apple`). `bond_push` no longer depends on `push`.

## 1. What it replaces

An app that gets its Apple token through a Firebase messaging plugin can use this for task notices. Keep Firebase where it
still serves something else. This package never reads an FCM token. The plugin is taken from pub.dev, not copied into
each app.

## 2. What the app adds

- An app with push on adds `bond_push_apple` next to `bond_push`. An app with push off adds neither the plugin nor
  `bond_push_apple`: `bond_tasks_notifications` and `bond_notify_powersync` pull in `bond_push` only, and `bond_push` does
  not link the plugin.

- On iOS: the Push Notifications capability on the app target.
- The environment, from the build configuration: `'sandbox'` for debug builds, `'production'` for release builds. The
  plugin cannot tell which Apple gateway a build talks to, and the server needs it to pick one.
- If the app also uses local notifications, set the notification-center delegate BEFORE the plugins register (in the app
  delegate, before `GeneratedPluginRegistrant.register`). The push plugin replaces the delegate and chains to the previous
  one. Without this, taps on local notifications may not arrive.
- A device id that survives launches, such as an install id (`deviceId`). A new id each launch fills the table with dead rows.
- A server with `POST /push/devices` and `DELETE /push/devices/{device_id}` (`bond_push_py.md`), or a sync store
  (`bond_notify_powersync.md`: `SyncPushDevices`).
- A moment to ask for permission. The package never asks by itself.

## 3. Smallest working example

```dart
import 'package:bond_push/bond_push.dart';
import 'package:bond_push_apple/bond_push_apple.dart';

final source = PluginPushTokenSource(environment: kReleaseMode ? 'production' : 'sandbox');
final registrar = PushRegistrar(source, PushDevicesApi(apiClient), deviceId: installId, topic: bundleId);

await source.requestPermission();   // the app decides when
await registrar.start();            // reads the token, retries while it is late, registers; never throws
// before sign-out:
await registrar.unregister();

final taps = PluginPushTaps();
final first = await taps.initialTap();        // the tap that launched the app, if any
taps.taps.listen((t) => open(t.route));       // taps while the app runs
```

Most apps do not write this by hand: `TaskAlertsCoordinator` takes the registrar and the taps (`bond_tasks_notifications.md`).

## 4. The pieces

- `PushTokenSource`: `token()`, `onRefresh`, `requestPermission()`. `PluginPushTokenSource` (in `bond_push_apple`) is the real one, `NoPushTokenSource`
  does nothing (tests, web).
- `PushDevices`: `register(token, deviceId:, topic:)` and `unregister(deviceId)`. `PushDevicesApi` calls the two REST routes.
- `PushRegistrar`: the Apple token arrives late, so it reads up to six times (the first read and 5 retries, 2 seconds apart),
  registers it, and registers again on every refresh. Failures go to its `errors` stream. Call `unregister()` before
  sign-out and `dispose()` when done.
- `PushTaps`: `taps` and `initialTap()`. The payload is `{notice_id, task_id, route}`. A payload without them is ignored.

## 5. Limits

- A remote notification has no action buttons: the plugin does not report which button was pressed, so `PushTap.action` is
  always null. A tap opens the task, where the banner offers Done, Snooze and Cancel. Local notifications keep the buttons.
- A debug build moving to a release build changes the environment. The registrar sends the row again on its next `start()`.
- Do not show a local notification AND a push for one notice. Pass `handledElsewhere` to the coordinator when push is on.

## 6. What to test

- `make -C packages/bond_push test` and `analyze` (registrar, over a fake `PushTokenSource`), and the same in `packages/bond_push_apple`.
  Tests inject a fake plugin: `PluginPushTokenSource(plugin: ...)` and `PluginPushTaps(plugin: ...)` take a `PushPlugin` from
  `package:bond_push_apple/bond_push_apple.dart`, so no platform channel is touched.
- A late token: `start()` registers once the token appears. A refresh registers again. `unregister()` stops listening.
- A payload missing `notice_id` is ignored.
- Not provable here: a real Apple push. It needs an Apple key and a physical device (`docs/test/MOBILE.md`).
