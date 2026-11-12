/// The push token seam: where a device token comes from.
library;

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

/// Token source over the pub.dev `push` plugin.
class PluginPushTokenSource implements PushTokenSource {
  PluginPushTokenSource({this.environment = 'production'});

  final String environment;

  @override
  Future<PushToken?> token() => throw UnimplementedError('PluginPushTokenSource.token is not implemented yet');

  @override
  Stream<PushToken> get onRefresh => throw UnimplementedError('PluginPushTokenSource.onRefresh is not implemented yet');

  @override
  Future<bool> requestPermission() => throw UnimplementedError('PluginPushTokenSource.requestPermission is not implemented yet');
}
