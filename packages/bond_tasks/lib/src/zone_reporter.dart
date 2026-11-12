/// Tells the server the device's time zone when it changes.
library;

import 'task_settings_api.dart';

abstract interface class TimeZoneSource {
  /// The device's IANA zone name, or null when unknown.
  Future<String?> currentZone();
}

class ZoneReporter {
  ZoneReporter(this.source, this.api);

  final TimeZoneSource source;
  final TaskSettingsApi api;

  Future<void> reportIfChanged() => throw UnimplementedError('ZoneReporter.reportIfChanged is not implemented yet');
}
