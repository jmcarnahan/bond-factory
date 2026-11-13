/// The local SQL writes of the task repository.
///
/// Column values written (the upload layer carries them; the server stays the authority):
/// - create: every stored column; `status` open, `completed_at` null, `created_by` the user,
///   `due_at` the device instant for a timed task and null for a date-only task (the server fills it).
/// - update: only the patched columns plus `updated_at`; `due_at` follows `due_date` / `due_time`
///   when they change (or the patch's own `dueAt`, for a timed result only; a date-only result writes null); clearing `due_date` also nulls `due_time` and `due_at`.
/// - complete: `status` done, `completed_at` now. reopen: `status` open, `completed_at` null.
///   cancel: `status` cancelled, `completed_at` null. Asking for the status the task already has writes nothing. All three also set `updated_at` and write
///   `_metadata` = `{"action": "complete" | "reopen" | "cancel"}` so the upload picks the route.
library;

import 'dart:convert';
import 'dart:math';

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_tasks/bond_tasks.dart';

import 'task_row.dart';
import 'task_table_shape.dart';
import 'tasks_tables.dart';

final RegExp kClientId = RegExp(r'^[A-Za-z0-9_-]{1,64}$');

/// A random v4 UUID string (letters, digits and dashes: a valid client id).
String newTaskId([Random? random]) {
  final r = random ?? Random.secure();
  final b = List<int>.generate(16, (_) => r.nextInt(256));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  final h = [for (final x in b) x.toRadixString(16).padLeft(2, '0')].join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}

String _checklist(List<ChecklistItem> l) => jsonEncode([for (final c in l) c.toJson()]);
String _links(List<TaskLink> l) => jsonEncode([for (final c in l) c.toJson()]);

/// The module-named columns of a new task (without `id`) and its id; validates the draft.
(String, Map<String, Object?>) buildInsert(
  TaskDraft d, {
  required String userId,
  required DateTime nowUtc,
  Set<String> extraColumns = const {},
}) {
  final problems = d.validate();
  if (problems.isNotEmpty) throw ArgumentError('invalid task draft: ${problems.map((p) => p.name).join(', ')}');
  final id = d.id ?? newTaskId();
  if (!kClientId.hasMatch(id)) throw ArgumentError.value(id, 'id', 'must match [A-Za-z0-9_-]{1,64}');
  final timed = d.dueDate != null && d.dueDate!.isNotEmpty && d.dueTime != null && d.dueTime!.isNotEmpty;
  final dueAt = timed ? (d.dueAt ?? deviceDueAt(d.dueDate, d.dueTime)) : null;
  final now = isoZ(nowUtc);
  return (id, {
    'owner_user_id': userId,
    'created_by': userId,
    'assigned_user_id': _blank(d.assignedUserId),
    'title': d.title.trim(),
    'notes': _blank(d.notes),
    'due_date': _blank(d.dueDate),
    'due_time': _blank(d.dueTime),
    'priority': d.priority?.wire,
    'due_at': dueAt == null ? null : isoZ(dueAt),
    'status': 'open',
    'completed_at': null,
    'checklist': _checklist(d.checklist),
    'remind_minutes_before': d.remindMinutesBefore,
    'mirror_enabled': d.mirrorEnabled ? 1 : 0,
    'mirror_status': 'pending',
    'links': _links(d.links),
    'source': d.source ?? 'manual',
    'created_at': now,
    'updated_at': now,
    ..._extraValues(d.extras, extraColumns),
  });
}

/// Module-named [values] as the local table names them: values of absent columns are dropped, renamed
/// columns take their local name, anything else (an extra column) passes through. Order is kept.
Map<String, Object?> localValues(TaskTableShape shape, Map<String, Object?> values) => {
      for (final e in values.entries)
        if (!kTaskColumns.contains(e.key))
          e.key: e.value
        else if (shape.has(e.key))
          shape.local(e.key): e.value,
    };

/// INSERT of local-named [values] for [id].
Future<void> executeInsert(SyncSql tx, String id, Map<String, Object?> values) async {
  final cols = ['id', ...values.keys];
  await tx.execute(
    'INSERT INTO $kTasksTable (${cols.join(', ')}) VALUES (${List.filled(cols.length, '?').join(', ')})',
    [id, ...values.values],
  );
}

/// INSERT of a new task; returns its id. Values of columns the [shape] marks absent are dropped.
Future<String> insertTask(
  SyncSql tx,
  TaskDraft d, {
  required String userId,
  required DateTime nowUtc,
  Set<String> extraColumns = const {},
  TaskTableShape shape = const TaskTableShape(),
}) async {
  final (id, values) = buildInsert(d, userId: userId, nowUtc: nowUtc, extraColumns: extraColumns);
  await executeInsert(tx, id, localValues(shape, values));
  return id;
}

/// The extras to store: only the declared [columns], with a bool as 0 or 1 and a list or map as JSON text.
Map<String, Object?> _extraValues(Map<String, Object?> extras, Set<String> columns) => {
      for (final c in columns)
        if (extras.containsKey(c))
          c: switch (extras[c]) {
            final bool b => b ? 1 : 0,
            final List<Object?> l => jsonEncode(l),
            final Map<Object?, Object?> m => jsonEncode(m),
            final v => v,
          },
    };

String? _blank(String? s) => s == null || s.isEmpty ? null : s;

/// The columns a [patch] changes (module names, in a fixed order), given the stored [row] (local names, read
/// through [shape]); empty when nothing changes. Absent columns are not dropped here: see `localValues`.
Map<String, Object?> patchColumns(
  SyncRow row,
  TaskPatch p, {
  Set<String> extraColumns = const {},
  TaskTableShape shape = const TaskTableShape(),
}) {
  final set = <String, Object?>{};
  if (p.title != null) set['title'] = p.title;
  if (p.notes != null) set['notes'] = _blank(p.notes!.value);
  if (p.dueDate != null) set['due_date'] = _blank(p.dueDate!.value);
  if (p.dueTime != null) set['due_time'] = _blank(p.dueTime!.value);
  if (p.assignedUserId != null) set['assigned_user_id'] = _blank(p.assignedUserId!.value);
  if (p.checklist != null) set['checklist'] = _checklist(p.checklist!);
  if (p.remindMinutesBefore != null) set['remind_minutes_before'] = p.remindMinutesBefore;
  if (p.mirrorEnabled != null) set['mirror_enabled'] = p.mirrorEnabled! ? 1 : 0;
  if (p.links != null) set['links'] = _links(p.links!);
  if (p.priority != null) set['priority'] = p.priority!.value?.wire;
  final oldDate = _blank(row[shape.local('due_date')] as String?), oldTime = _blank(row[shape.local('due_time')] as String?);
  final newDate = p.dueDate != null ? _blank(p.dueDate!.value) : oldDate;
  var newTime = p.dueTime != null ? _blank(p.dueTime!.value) : oldTime;
  if (newDate == null && newTime != null) {
    // A time without a date is invalid: clearing the date clears the time too.
    newTime = null;
    set['due_time'] = null;
  }
  // The device writes a due instant only for a timed task (date and time both set after the patch).
  // A date-only result gets null: the server computes its end-of-day instant.
  final timed = newDate != null && newTime != null;
  if (p.dueAt != null && timed) {
    final at = p.dueAt!.value ?? deviceDueAt(newDate, newTime);
    set['due_at'] = at == null ? null : isoZ(at);
  } else if (newDate != oldDate || newTime != oldTime) {
    final at = timed ? deviceDueAt(newDate, newTime) : null;
    set['due_at'] = at == null ? null : isoZ(at);
  }
  set.addAll(_extraValues(p.extras, extraColumns));
  return set;
}

/// UPDATE of local-named [values] (which already hold `updated_at`); no statement when empty.
Future<void> executeUpdate(SyncSql tx, String id, Map<String, Object?> values) async {
  if (values.isEmpty) return;
  await tx.execute(
    'UPDATE $kTasksTable SET ${values.keys.map((c) => '$c = ?').join(', ')} WHERE id = ?',
    [...values.values, id],
  );
}

/// UPDATE of only [set] (module names; absent columns dropped) plus `updated_at`; no statement when [set] is empty.
Future<void> updateColumns(
  SyncSql tx,
  String id,
  Map<String, Object?> set,
  DateTime nowUtc, {
  TaskTableShape shape = const TaskTableShape(),
}) async {
  if (set.isEmpty) return;
  await executeUpdate(tx, id, {...localValues(shape, set), shape.local('updated_at'): isoZ(nowUtc)});
}

/// The local-named values of a status action: status, `completed_at`, then (with [writeCompletedBy] and the
/// column present) `completed_by` (the user on complete, null otherwise), then `updated_at`.
Map<String, Object?> statusValues(
  String action,
  DateTime nowUtc, {
  TaskTableShape shape = const TaskTableShape(),
  bool writeCompletedBy = false,
  String? userId,
}) {
  final (status, completed) = switch (action) {
    'complete' => ('done', isoZ(nowUtc)),
    'reopen' => ('open', null),
    _ => ('cancelled', null),
  };
  return {
    shape.local('status'): status,
    shape.local('completed_at'): completed,
    if (writeCompletedBy && shape.has('completed_by')) shape.local('completed_by'): action == 'complete' ? userId : null,
    shape.local('updated_at'): isoZ(nowUtc),
  };
}

/// UPDATE of a status action's local-named [values]; `_metadata` carries the action so the upload picks the route.
Future<void> executeStatus(SyncSql tx, String id, String action, Map<String, Object?> values) => tx.execute(
      'UPDATE $kTasksTable SET ${values.keys.map((c) => '$c = ?').join(', ')}, _metadata = ? WHERE id = ?',
      [...values.values, jsonEncode({'action': action}), id],
    );

/// UPDATE for complete (`done`), reopen (`open`) and cancel (`cancelled`).
Future<void> setStatus(
  SyncSql tx,
  String id,
  String action,
  DateTime nowUtc, {
  TaskTableShape shape = const TaskTableShape(),
  bool writeCompletedBy = false,
  String? userId,
}) =>
    executeStatus(tx, id, action, statusValues(action, nowUtc, shape: shape, writeCompletedBy: writeCompletedBy, userId: userId));
