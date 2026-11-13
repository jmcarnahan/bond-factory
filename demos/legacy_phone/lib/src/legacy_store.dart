/// The adopter recipe: the SDK task store over the app's own `tasks` table. Built only from the repository's seams.
library;

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';

import 'legacy_schema.dart';

PowerSyncTaskRepository legacyTaskRepository(
  SyncDb db, {
  required String userId,
  required LegacyStage stage,
  TaskClock clock = const TaskClock(),
}) =>
    PowerSyncTaskRepository(
      db,
      userId: userId,
      clock: clock,
      // The table: nine columns missing until the app adds them; the flag lives in `sync_to_calendar`.
      shape: TaskTableShape(
        absent: stage == LegacyStage.asShipped ? kMissingColumns.toSet() : const {},
        rename: const {'mirror_enabled': 'sync_to_calendar'},
        dueOrder: stage == LegacyStage.widened ? TaskDueOrder.dateThenTime : null, // old rows have no `due_at`
      ),
      extraColumns: const {'client_ref', 'case_ref', 'case_file_no'},
      extraWatchTables: const ['users', 'clients', 'cases'],
      enricher: _names,
      // A row with no stored state (written before the app had one) shows what a write would give it.
      mirrorStatusFor: (row) => _s(row['mirror_status']) == null ? _mirror(row, null) : null,
      mirrorStatusOnWrite: _mirror,
      writeCompletedBy: true,
      prepare: _rules,
      afterWrite: (tx, w) => tx.execute("DELETE FROM sync_rejections WHERE table_name = 'tasks' AND row_id = ?", [w.id]),
    );

String? _s(Object? v) => v is String && v.trim().isNotEmpty ? v.trim() : null;

/// One rule for reads and writes: a dated, open task with the flag on (NULL is on) waits for the calendar.
String _mirror(SyncRow after, SyncRow? before) {
  final eligible = after['sync_to_calendar'] != 0 && _s(after['due_date']) != null && after['status'] == 'open';
  return eligible || before?['mirror_status'] == 'mirrored' ? 'pending' : 'skipped';
}

/// One query per table over the ids in the page.
Future<List<Task>> _names(SyncSql sql, List<Task> tasks) async {
  Future<Map<String, SyncRow>> byId(String table, String cols, Iterable<String?> ids) async {
    final set = {for (final i in ids) if (_s(i) != null) i!};
    if (set.isEmpty) return {};
    final rows = await sql.getAll('SELECT id, $cols FROM $table WHERE id IN (${List.filled(set.length, '?').join(', ')})', [...set]);
    return {for (final r in rows) r['id']! as String: r};
  }

  final users = await byId('users', 'name, email', [for (final t in tasks) ...[t.ownerUserId, t.assignedUserId]]);
  final clients = await byId('clients', 'first_name, last_name', [for (final t in tasks) t.extras['client_ref'] as String?]);
  final cases = await byId('cases', 'label', [for (final t in tasks) t.extras['case_ref'] as String?]);
  String? user(String? id) => users[id] == null ? null : _s(users[id]!['name']) ?? _s(users[id]!['email']);
  String? client(String? id) {
    final r = clients[id];
    final name = r == null ? '' : '${_s(r['first_name']) ?? ''} ${_s(r['last_name']) ?? ''}'.trim();
    return name.isEmpty ? null : name;
  }

  return [
    for (final t in tasks)
      t.copyWith(
        ownerName: user(t.ownerUserId),
        assigneeName: user(t.assignedUserId),
        extras: {
          ...t.extras,
          'client_name': client(t.extras['client_ref'] as String?),
          'case_label': cases[t.extras['case_ref']]?['label'],
        },
      ),
  ];
}

/// The app's rules, inside the write transaction: blank links are NULL, a case implies its client (and a case of
/// another client is refused), and `case_file_no` follows the case.
Future<Map<String, Object?>> _rules(SyncSql tx, TaskWrite w) async {
  final v = {...w.values};
  for (final k in const ['client_ref', 'case_ref']) {
    if (v.containsKey(k)) v[k] = _s(v[k]);
  }
  if (!v.containsKey('case_ref')) return v;
  final c = v['case_ref'] == null ? null : await tx.getOptional('SELECT client_id, file_no FROM cases WHERE id = ?', [v['case_ref']]);
  final client = v.containsKey('client_ref') ? v['client_ref'] : _s(w.before?['client_ref']);
  if (c != null && client != null && c['client_id'] != client) throw StateError('case_belongs_to_another_client');
  if (c != null && client == null) v['client_ref'] = c['client_id'];
  if (!v.containsKey('case_file_no')) v['case_file_no'] = c?['file_no'];
  return v;
}
