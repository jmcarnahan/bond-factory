/// The device zone from flutter_timezone.
library;

import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_timezone/flutter_timezone.dart';

class FlutterTimeZoneSource implements TimeZoneSource {
  FlutterTimeZoneSource();

  /// The IANA zone id of the device, or null when it cannot be read.
  @override
  Future<String?> currentZone() async {
    try {
      final id = (await FlutterTimezone.getLocalTimezone()).identifier;
      return id.isEmpty ? null : id;
    } catch (_) {
      return null;
    }
  }
}
