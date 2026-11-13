/// The synced per-user settings table and the checks of its names.
library;

import 'package:powersync/powersync.dart';

import 'extra_names.dart';

/// The default name of the synced settings table (the server's `task_user_settings`; its row id is the user id).
const String kTaskSettingsTable = 'task_user_settings';

/// The wire names of the four settings. `lead_minutes` is an integer column, the rest are text.
const List<String> kTaskSettingsColumns = ['time_zone', 'start_of_day', 'end_of_day', 'lead_minutes'];

final RegExp _safe = RegExp(r'^[a-z_][a-z0-9_]*$');

/// Throws [ArgumentError] unless [table] is a plain lower-case name that SQLite takes unquoted.
void checkSettingsTable(String table) {
  if (!_safe.hasMatch(table)) throw ArgumentError.value(table, 'table', 'must match ^[a-z_][a-z0-9_]*\$');
  if (kSqliteKeywords.contains(table)) throw ArgumentError.value(table, 'table', 'is an SQL keyword');
}

/// Throws [ArgumentError] when a [rename] key is not one of [kTaskSettingsColumns] or a local name is unsafe, an SQL keyword,
/// `id`, `_metadata`, another wire name (other than its own) or used twice.
void checkSettingsRename(Map<String, String> rename) {
  final seen = <String>{};
  for (final e in rename.entries) {
    if (!kTaskSettingsColumns.contains(e.key)) throw ArgumentError.value(e.key, 'rename', 'is not a settings column');
    final n = e.value;
    if (!_safe.hasMatch(n)) throw ArgumentError.value(n, 'rename', 'must match ^[a-z_][a-z0-9_]*\$');
    if (n == 'id' || n == '_metadata') throw ArgumentError.value(n, 'rename', 'is reserved');
    if (kSqliteKeywords.contains(n)) throw ArgumentError.value(n, 'rename', 'is an SQL keyword');
    if (n != e.key && kTaskSettingsColumns.contains(n)) throw ArgumentError.value(n, 'rename', 'is another settings column');
    if (!seen.add(n)) throw ArgumentError.value(n, 'rename', 'used twice');
  }
}

/// The settings table to add to the app schema: one row per user, id = the user id; `lead_minutes` is an integer, the rest
/// text. [table] is the local table name and [rename] maps a wire name (see [kTaskSettingsColumns]) to the local column that
/// holds it, for an app whose table already exists. Names are checked like `TaskTableShape.rename`: [ArgumentError] otherwise.
List<Table> taskSettingsTables({String table = kTaskSettingsTable, Map<String, String> rename = const {}}) {
  checkSettingsTable(table);
  checkSettingsRename(rename);
  return [
    Table(table, [
      for (final c in kTaskSettingsColumns)
        c == 'lead_minutes' ? Column.integer(rename[c] ?? c) : Column.text(rename[c] ?? c),
    ]),
  ];
}
