/// The push token source over the pub.dev `push` plugin.
library;

import 'dart:async';

import 'package:bond_push/bond_push.dart';

import 'push_plugin.dart';

/// Token source over the pub.dev `push` plugin (iOS: the Apple device token).
///
/// [environment] is `sandbox` for debug builds and `production` for release
/// builds; the plugin cannot tell, so the app passes it. [plugin] is for tests.
class PluginPushTokenSource implements PushTokenSource {
  PluginPushTokenSource({this.environment = 'production', PushPlugin? plugin})
      : _plugin = plugin ?? const DefaultPushPlugin();

  final String environment;
  final PushPlugin _plugin;

  PushToken _make(String value) => PushToken(value: value, environment: environment);

  @override
  Future<PushToken?> token() async {
    final v = await _plugin.getToken();
    return v == null || v.isEmpty ? null : _make(v);
  }

  @override
  Stream<PushToken> get onRefresh {
    void Function()? off;
    late StreamController<PushToken> c;
    c = StreamController<PushToken>.broadcast(
      onListen: () => off = _plugin.addOnNewToken((t) {
        if (t.isNotEmpty) c.add(_make(t));
      }),
      onCancel: () {
        off?.call();
        off = null;
      },
    );
    return c.stream;
  }

  @override
  Future<bool> requestPermission() => _plugin.requestPermission();
}
