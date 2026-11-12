# bond_push

Apple push for the bond apps: the device token, registering it with the service, and taps on a push.
The seams and the plain classes. The pub.dev `push` plugin is in `bond_push_apple`, so an app with push off
links no plugin. iOS only; Android is not supported.

```dart
import 'package:bond_push/bond_push.dart';
import 'package:bond_push_apple/bond_push_apple.dart'; // PluginPushTokenSource, PluginPushTaps

final source = PluginPushTokenSource(environment: kReleaseMode ? 'production' : 'sandbox');
final registrar = PushRegistrar(source, PushDevicesApi(apiClient), deviceId: installId);

await source.requestPermission(); // the app decides when to ask
await registrar.start();          // reads the token, retries while it is late, registers
// before sign-out:
await registrar.unregister();

final taps = PluginPushTaps();
final first = await taps.initialTap();        // the tap that launched the app, if any
taps.taps.listen((t) => open(t.route));       // taps while the app runs
```

## The pieces

- `PushTokenSource`: `token()`, `onRefresh`, `requestPermission()`. `PluginPushTokenSource` (in `bond_push_apple`) is the real one,
  `NoPushTokenSource` is inert (tests, web).
- `PushDevices`: `register` and `unregister`; `PushDevicesApi` calls `POST /push/devices` and
  `DELETE /push/devices/{device_id}`.
- `PushRegistrar`: `start()` never asks for permission and never throws. The Apple token arrives late, so it
  reads the token up to six times (the first read, then 5 retries 2 seconds apart), registers it, and registers
  again on every refresh. Failures go to its `errors` stream. `unregister()` stops listening and tells the
  service; call it before sign-out. `dispose()` when done.
- `PushTaps`: `taps` and `initialTap()`. The push payload is `{notice_id, task_id, route}`; a `PushTap` carries
  `route` and `noticeId`. A payload without them is not ours and is ignored.

## What the app must do on iOS

- Enable the Push Notifications capability for the app target.
- Pass `environment: 'sandbox'` for debug builds and `'production'` for release builds. The plugin cannot tell
  which Apple gateway a build talks to, and the server needs it to pick one.
- The device row (sent over REST by `PushDevicesApi`, or written for sync by a sync-store `PushDevices`) carries
  `platform`, `environment` and `topic`. Moving from a debug to a release build changes the environment; the
  registrar sends the row again, with the new environment, on its next `start()`.
- If the app also uses local notifications (`flutter_local_notifications`), set the notification-center
  delegate BEFORE the plugins register, so taps on local notifications still arrive. Two plugins that both take
  the delegate can otherwise fight over taps.

## Limits in this version

- A remote notification has no action buttons: the plugin does not report which button was pressed, so
  `PushTap.action` is always null and a tap opens the task.
- Android is not supported.

## Tests

`PluginPushTokenSource` and `PluginPushTaps` take an optional `plugin` (a `PushPlugin`, from
`package:bond_push_apple/bond_push_apple.dart`) so tests inject a fake and never touch a platform channel.
