/// `GET /tasks/settings` and `PUT /tasks/settings`.
library;

import 'package:bond_json/bond_json.dart';

/// The wire names of the four settings, in the order `overridden` lists them.
const List<String> kTaskSettingFields = ['time_zone', 'start_of_day', 'end_of_day', 'lead_minutes'];

class TaskSettings {
  const TaskSettings({
    this.timeZone,
    this.startOfDay = '08:00',
    this.endOfDay = '17:00',
    this.leadMinutes = 60,
    this.warnings = const [],
    this.overridden,
  });

  factory TaskSettings.fromJson(Map<String, Object?> m) => TaskSettings(
        timeZone: jstr(m, 'time_zone'),
        startOfDay: jstr(m, 'start_of_day') ?? '08:00',
        endOfDay: jstr(m, 'end_of_day') ?? '17:00',
        leadMinutes: jint(m, 'lead_minutes') ?? 60,
        warnings: jlist(m, 'warnings', (o) => o.toString()),
        overridden: m.containsKey('overridden') && m['overridden'] != null
            ? {...jlist(m, 'overridden', (o) => o.toString())}
            : null,
      );

  final String? timeZone;

  /// `HH:MM`.
  final String startOfDay;
  final String endOfDay;
  final int leadMinutes;
  final List<String> warnings;

  /// The wire names of the fields the user has set (the rest follow the app default).
  /// Null when the server did not say (an older server).
  final Set<String>? overridden;

  /// True when the server said which fields are overridden.
  bool get overriddenKnown => overridden != null;

  /// True when the user set [field] (a wire name such as `end_of_day`). False when unknown.
  bool isOverridden(String field) => overridden?.contains(field) ?? false;

  Map<String, Object?> toJson() => {
        'time_zone': timeZone,
        'start_of_day': startOfDay,
        'end_of_day': endOfDay,
        'lead_minutes': leadMinutes,
        'warnings': warnings,
        if (overridden != null) 'overridden': [for (final f in kTaskSettingFields) if (overridden!.contains(f)) f],
      };
}

/// The body of `PUT /tasks/settings`: only the fields set are sent. A wire name in [reset] is sent
/// as an explicit null (back to the app default) and wins over a value given for the same field.
class TaskSettingsPatch {
  const TaskSettingsPatch({this.timeZone, this.startOfDay, this.endOfDay, this.leadMinutes, this.reset = const {}});

  final Set<String> reset;

  final String? timeZone;
  final String? startOfDay;
  final String? endOfDay;
  final int? leadMinutes;

  Map<String, Object?> toJson() => {
        if (reset.contains('time_zone')) 'time_zone': null else if (timeZone != null) 'time_zone': timeZone,
        if (reset.contains('start_of_day')) 'start_of_day': null else if (startOfDay != null) 'start_of_day': startOfDay,
        if (reset.contains('end_of_day')) 'end_of_day': null else if (endOfDay != null) 'end_of_day': endOfDay,
        if (reset.contains('lead_minutes')) 'lead_minutes': null else if (leadMinutes != null) 'lead_minutes': leadMinutes,
      };
}
