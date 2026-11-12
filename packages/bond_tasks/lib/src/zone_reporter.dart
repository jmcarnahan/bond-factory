/// Tells the server the device's time zone when it changes.
library;

import 'task_settings.dart';
import 'task_settings_api.dart';

abstract interface class TimeZoneSource {
  /// The device's IANA zone name, or null when unknown.
  Future<String?> currentZone();
}

/// Sends `{time_zone}` to the settings route when the device zone differs from the last value the
/// server accepted. The first call reads the stored zone (a GET) so a restart does not re-send it.
/// A failed GET or PUT is not thrown (this runs in the background): the last value stays as it was
/// and the next call tries again.
class ZoneReporter {
  ZoneReporter(this.source, this.api);

  final TimeZoneSource source;
  final TaskSettingsApi api;

  String? _sent;
  bool _seeded = false;

  Future<void> reportIfChanged() async {
    final zone = await source.currentZone();
    if (zone == null || zone.isEmpty) return;
    if (!_seeded) {
      try {
        _sent = (await api.get()).timeZone;
        _seeded = true;
      } catch (_) {
        // Stored zone unknown: send anyway; the seed is retried on the next call.
      }
    }
    if (zone == _sent) return;
    try {
      await api.update(TaskSettingsPatch(timeZone: zone));
      _sent = zone;
    } catch (_) {
      // Left unchanged: the next call retries.
    }
  }
}
