/// [TaskSettingsStore] over the synced settings row of the user.
library;

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_tasks/bond_tasks.dart';

import 'task_settings_tables.dart';

final RegExp _hhmm = RegExp(r'^([01]\d|2[0-3]):[0-5]\d$');

/// Reads and writes the user's settings in the local store (`taskSettingsTables`); the sync upload carries the writes.
///
/// One row per user, its id is [userId]. A NULL cell, or no row, reads as the app default from [defaults]; `overridden` is
/// the wire names whose cell is not NULL (empty with no row); `warnings` is always empty (the server's warnings do not
/// travel over sync). `update` with no row inserts `(id, <only the columns the patch sets or resets>)` (a queued put); with a
/// row it updates only those columns (a queued patch). A name in the patch's `reset` writes NULL and wins over a value; an
/// empty patch writes nothing. `start_of_day` and `end_of_day` must be `HH:MM` and `lead_minutes` 0..10080 (the server's range),
/// else [ArgumentError] and nothing is written. The time zone is NOT checked here: the server refuses a bad zone and the next
/// download restores the row.
/// It returns the settings as read back.
class PowerSyncTaskSettingsStore implements TaskSettingsStore {
  PowerSyncTaskSettingsStore(
    this.db, {
    required this.userId,
    this.defaults = const TaskSettings(),
    this.table = kTaskSettingsTable,
    Map<String, String> rename = const {},
  }) : rename = Map.unmodifiable(rename) {
    checkSettingsTable(table);
    checkSettingsRename(this.rename);
  }

  final SyncDb db;
  final String userId;

  /// What a field reads as while the user has not set it.
  final TaskSettings defaults;
  final String table;

  /// Wire name to the local column that holds it.
  final Map<String, String> rename;

  String _col(String wire) => rename[wire] ?? wire;

  Future<TaskSettings> _read(SyncSql sql) async {
    final row = await sql.getOptional('SELECT * FROM $table WHERE id = ?', [userId]);
    if (row == null) return _decode(const {});
    return _decode({for (final c in kTaskSettingsColumns) c: row[_col(c)]});
  }

  TaskSettings _decode(Map<String, Object?> cells) {
    int? lead(Object? v) => v is num ? v.toInt() : (v is String ? int.tryParse(v.trim()) : null);
    String? text(Object? v) => v is String && v.isNotEmpty ? v : null;
    final tz = text(cells['time_zone']), start = text(cells['start_of_day']), end = text(cells['end_of_day']);
    final l = lead(cells['lead_minutes']);
    return TaskSettings(
      timeZone: tz ?? defaults.timeZone,
      startOfDay: start ?? defaults.startOfDay,
      endOfDay: end ?? defaults.endOfDay,
      leadMinutes: l ?? defaults.leadMinutes,
      warnings: const [],
      overridden: {
        if (tz != null) 'time_zone',
        if (start != null) 'start_of_day',
        if (end != null) 'end_of_day',
        if (l != null) 'lead_minutes',
      },
    );
  }

  @override
  Future<TaskSettings> get() => readSnapshot(db, _read);

  /// The settings as a live snapshot: again after every change to the table, local or synced.
  Stream<TaskSettings> watch() => watchSnapshot(db, [table], _read);

  @override
  Future<TaskSettings> update(TaskSettingsPatch p) async {
    final values = <String, Object?>{};
    void put(String wire, Object? v) {
      if (p.reset.contains(wire)) {
        values[_col(wire)] = null;
      } else if (v != null) {
        values[_col(wire)] = v;
      }
    }

    final lead = p.leadMinutes;
    if (lead != null && !p.reset.contains('lead_minutes') && (lead < 0 || lead > 10080)) {
      throw ArgumentError.value(lead, 'lead_minutes', 'must be 0..10080');
    }
    for (final f in [('start_of_day', p.startOfDay), ('end_of_day', p.endOfDay)]) {
      final v = f.$2;
      if (v != null && !p.reset.contains(f.$1) && !_hhmm.hasMatch(v)) throw ArgumentError.value(v, f.$1, 'must be HH:MM');
    }
    put('time_zone', p.timeZone);
    put('start_of_day', p.startOfDay);
    put('end_of_day', p.endOfDay);
    put('lead_minutes', p.leadMinutes);
    return await db.writeTransaction((tx) async {
      if (values.isNotEmpty) {
        final exists = await tx.getOptional('SELECT id FROM $table WHERE id = ?', [userId]) != null;
        if (exists) {
          await tx.execute('UPDATE $table SET ${values.keys.map((c) => '$c = ?').join(', ')} WHERE id = ?', [...values.values, userId]);
        } else {
          final cols = ['id', ...values.keys];
          await tx.execute(
            'INSERT INTO $table (${cols.join(', ')}) VALUES (${List.filled(cols.length, '?').join(', ')})',
            [userId, ...values.values],
          );
        }
      }
      return _read(tx);
    });
  }
}
