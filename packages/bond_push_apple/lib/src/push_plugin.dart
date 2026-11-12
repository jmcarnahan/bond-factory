/// The calls bond_push_apple makes on the `push` plugin, behind a seam so tests
/// never touch a platform channel.
library;

import 'package:push/push.dart';

abstract interface class PushPlugin {
  /// The Apple device token as a hex string, or null.
  Future<String?> getToken();

  /// Subscribes to token refreshes; returns the unsubscribe call.
  void Function() addOnNewToken(void Function(String token) handler);

  Future<bool> requestPermission();

  /// Subscribes to taps on a remote notification while the app is running;
  /// returns the unsubscribe call.
  void Function() addOnNotificationTap(void Function(Map<String?, Object?> payload) handler);

  /// The tap that launched the app from a terminated state, or null.
  Future<Map<String?, Object?>?> launchTap();
}

/// Calls `Push.instance` on each use, so merely constructing it is harmless.
class DefaultPushPlugin implements PushPlugin {
  const DefaultPushPlugin();

  @override
  Future<String?> getToken() => Push.instance.token;

  @override
  void Function() addOnNewToken(void Function(String token) handler) => Push.instance.addOnNewToken(handler);

  @override
  Future<bool> requestPermission() => Push.instance.requestPermission();

  @override
  void Function() addOnNotificationTap(void Function(Map<String?, Object?> payload) handler) =>
      Push.instance.addOnNotificationTap(handler);

  @override
  Future<Map<String?, Object?>?> launchTap() => Push.instance.notificationTapWhichLaunchedAppFromTerminated;
}
