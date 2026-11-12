import 'dart:convert';
import 'dart:io';

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_sync_powersync/testing.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';

Map<String, Object?> fixture(String name) =>
    (jsonDecode(File('../../fixtures/tasks/$name').readAsStringSync()) as Map).cast<String, Object?>();

/// A fixture task in the form the store holds: JSON as text, booleans as 0/1, no derived or name columns.
SyncRow rowOf(Map<String, Object?> task) {
  final r = {...task}
    ..remove('owner_name')
    ..remove('assignee_name')
    ..remove('overdue');
  for (final k in const ['checklist', 'links']) {
    r[k] = jsonEncode(r[k]);
  }
  r['mirror_enabled'] = (r['mirror_enabled'] as bool? ?? true) ? 1 : 0;
  return r;
}

/// Every column the tasks table declares, from the real table definition.
Set<String> taskColumnNames() {
  final t = tasksTables().single;
  return {'id', for (final c in t.columns) c.name, '_metadata'};
}

FakeSyncDb fakeTasks(List<SyncRow> rows) => FakeSyncDb.tables(
      {'tasks': rows},
      applySql: true,
      columns: {'tasks': taskColumnNames()},
    );

PowerSyncTaskRepository repoFor(FakeSyncDb db, {String user = 'user-1', required DateTime now}) =>
    PowerSyncTaskRepository(db, userId: user, clock: TaskClock(() => now));

/// True when the machine zone is America/Los_Angeles on the fixture's day.
bool inLosAngeles() => DateTime.utc(2026, 3, 11, 20).toLocal().timeZoneOffset == const Duration(hours: -7);

const String kZoneSkip = 'needs TZ=America/Los_Angeles (the director runs with TZ set)';
