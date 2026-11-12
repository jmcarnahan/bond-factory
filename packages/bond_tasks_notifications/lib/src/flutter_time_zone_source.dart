/// The device zone from flutter_timezone.
library;

import 'package:bond_tasks/bond_tasks.dart';

class FlutterTimeZoneSource implements TimeZoneSource {
  FlutterTimeZoneSource();

  @override
  Future<String?> currentZone() => throw UnimplementedError('FlutterTimeZoneSource.currentZone is not implemented yet');
}
