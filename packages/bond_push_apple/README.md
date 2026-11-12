# bond_push_apple

The pub.dev `push` plugin behind the `bond_push` seams. iOS only. Add this package only in an app that uses
Apple push. An app with push off depends on `bond_push` alone (or not at all) and links no push plugin.

```dart
import 'package:bond_push/bond_push.dart';
import 'package:bond_push_apple/bond_push_apple.dart';

final source = PluginPushTokenSource(environment: kReleaseMode ? 'production' : 'sandbox');
final registrar = PushRegistrar(source, PushDevicesApi(apiClient), deviceId: installId);
final taps = PluginPushTaps();
```

## What is here

- `PluginPushTokenSource`: a `PushTokenSource` over the plugin. The app passes `environment` (`sandbox` for
  debug builds, `production` for release builds); the plugin cannot tell.
- `PluginPushTaps`: a `PushTaps` over the plugin. `PushTap.action` is always null, because the plugin does not
  report which action button was pressed.
- `PushPlugin`, `DefaultPushPlugin`: the four plugin calls behind a seam. Both classes take an optional `plugin:`
  so tests inject a fake and never touch a platform channel.

The iOS setup (Push Notifications capability, notification-center delegate order) is in the `bond_push` README.
