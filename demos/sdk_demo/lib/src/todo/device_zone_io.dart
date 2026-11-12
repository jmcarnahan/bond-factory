import 'dart:io' show Platform;

/// The device's IANA zone name. Off the web the platform does not expose one
/// without a plugin, so the demo reads the `TZ` variable (tests set it); null
/// when it is not set, and the server then keeps the person's stored zone.
String? deviceZoneName() {
  final tz = Platform.environment['TZ'];
  return tz == null || tz.isEmpty ? null : tz;
}
