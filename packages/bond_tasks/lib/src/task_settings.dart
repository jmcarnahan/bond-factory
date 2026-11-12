/// `GET /tasks/settings` and `PUT /tasks/settings`.
library;

import 'package:bond_json/bond_json.dart';

class TaskSettings {
  const TaskSettings({
    this.timeZone,
    this.startOfDay = '08:00',
    this.endOfDay = '17:00',
    this.leadMinutes = 60,
    this.warnings = const [],
  });

  factory TaskSettings.fromJson(Map<String, Object?> m) => TaskSettings(
        timeZone: jstr(m, 'time_zone'),
        startOfDay: jstr(m, 'start_of_day') ?? '08:00',
        endOfDay: jstr(m, 'end_of_day') ?? '17:00',
        leadMinutes: jint(m, 'lead_minutes') ?? 60,
        warnings: jlist(m, 'warnings', (o) => o.toString()),
      );

  final String? timeZone;

  /// `HH:MM`.
  final String startOfDay;
  final String endOfDay;
  final int leadMinutes;
  final List<String> warnings;

  Map<String, Object?> toJson() => {
        'time_zone': timeZone,
        'start_of_day': startOfDay,
        'end_of_day': endOfDay,
        'lead_minutes': leadMinutes,
        'warnings': warnings,
      };
}

/// The body of `PUT /tasks/settings`: only the fields set are sent.
class TaskSettingsPatch {
  const TaskSettingsPatch({this.timeZone, this.startOfDay, this.endOfDay, this.leadMinutes});

  final String? timeZone;
  final String? startOfDay;
  final String? endOfDay;
  final int? leadMinutes;

  Map<String, Object?> toJson() => {
        if (timeZone != null) 'time_zone': timeZone,
        if (startOfDay != null) 'start_of_day': startOfDay,
        if (endOfDay != null) 'end_of_day': endOfDay,
        if (leadMinutes != null) 'lead_minutes': leadMinutes,
      };
}
