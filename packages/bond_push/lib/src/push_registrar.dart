/// Keeps the device registered: retries while the token is late, re-registers on refresh.
library;

import 'push_devices.dart';
import 'push_token.dart';

class PushRegistrar {
  PushRegistrar(this.source, this.devices, {required this.deviceId, this.topic});

  final PushTokenSource source;
  final PushDevices devices;
  final String deviceId;
  final String? topic;

  /// Registers now (with retries) and again on every token refresh.
  Future<void> start() => throw UnimplementedError('PushRegistrar.start is not implemented yet');

  /// Unregisters the device; call before sign-out.
  Future<void> unregister() => throw UnimplementedError('PushRegistrar.unregister is not implemented yet');

  void dispose() {}
}
