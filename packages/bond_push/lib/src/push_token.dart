/// The push token seam: where a device token comes from.
library;

import 'dart:async';

import 'push_plugin.dart';

/// An Apple push token with the channel it belongs to.
class PushToken {
  const PushToken({required this.value, this.platform = 'ios', this.environment = 'production'});

  /// The hex token string.
  final String value;

  /// Always `ios` (the phones are iOS only).
  final String platform;

  /// `production` or `sandbox` (the Apple push environment this build talks to).
  final String environment;

  Map<String, Object?> toJson() => {'token': value, 'platform': platform, 'environment': environment};

  @override
  bool operator ==(Object other) =>
      other is PushToken && other.value == value && other.platform == platform && other.environment == environment;

  @override
  int get hashCode => Object.hash(value, platform, environment);
}

abstract interface class PushTokenSource {
  /// The current token, or null when none is known (no permission, simulator, not yet issued).
  Future<PushToken?> token();

  /// Fires when the system issues a new token.
  Stream<PushToken> get onRefresh;

  /// Asks the person for notification permission; true when granted.
  Future<bool> requestPermission();
}

/// No push: token null, permission refused, nothing ever refreshes.
class NoPushTokenSource implements PushTokenSource {
  const NoPushTokenSource();

  @override
  Future<PushToken?> token() async => null;

  @override
  Stream<PushToken> get onRefresh => const Stream<PushToken>.empty();

  @override
  Future<bool> requestPermission() async => false;
}

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
