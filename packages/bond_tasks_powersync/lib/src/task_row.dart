/// A synced `tasks` row to a [Task].
library;

import 'dart:convert';

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_tasks/bond_tasks.dart';

import 'task_table_shape.dart';
import 'tasks_tables.dart';

/// UTC ISO-8601 with milliseconds and a trailing Z, the form the server writes.
String isoZ(DateTime t) => DateTime.fromMillisecondsSinceEpoch(t.millisecondsSinceEpoch, isUtc: true).toIso8601String();

/// Decodes a stored datetime (a missing Z means UTC); null when empty or unreadable.
String? _time(Object? v) {
  if (v is! String || v.trim().isEmpty) return null;
  var s = v.trim();
  if (!RegExp(r'(Z|[+-]\d{2}(:?\d{2})?)$', caseSensitive: false).hasMatch(s) || RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(s)) {
    s = RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(s) ? '${s}T00:00:00Z' : '${s}Z';
  }
  final d = DateTime.tryParse(s);
  return d == null ? null : isoZ(d);
}

/// Gives the mirror state to show for a stored row, as a `MirrorStatus` wire value, or null to keep
/// the stored one. See `PowerSyncTaskRepository.mirrorStatusFor`.
typedef MirrorStatusFor = String? Function(SyncRow row);

String? _mirror(SyncRow row, MirrorStatusFor? hook, TaskTableShape shape) {
  if (hook != null) {
    try {
      final v = hook(row);
      if (v != null) return v;
    } catch (_) {
      // keep the stored value for this row
    }
  }
  return shape.has('mirror_status') ? _str(row[shape.local('mirror_status')]) : null;
}

String? _str(Object? v) => v?.toString();

/// Like [_str] but the empty string reads as null (a note keeps its spaces).
String? _empty(Object? v) {
  final s = v?.toString();
  return s == null || s.isEmpty ? null : s;
}

/// Like [_str] but a blank string reads as null (rows an old build wrote).
String? _nb(Object? v) {
  final s = v?.toString();
  return s == null || s.trim().isEmpty ? null : s;
}

int? _int(Object? v) {
  if (v is int) return v;
  if (v is num) return v.isFinite ? v.truncate() : null;
  if (v is String) return int.tryParse(v.trim());
  return null;
}

/// The cell's JSON list; a missing, malformed or non-list cell is an empty list. Elements that
/// [keep] rejects are dropped.
List<Object?> _list(Object? cell, bool Function(Object?) keep) {
  Object? v = cell;
  if (v is String) {
    try {
      v = jsonDecode(v);
    } catch (_) {
      return const [];
    }
  }
  if (v is! List) return const [];
  return [
    for (final e in v)
      if (keep(e)) e,
  ];
}

bool _ok(Object? e, void Function(Object?) parse) {
  try {
    parse(e);
    return true;
  } catch (_) {
    return false;
  }
}

final Set<String> _known = {'id', '_metadata', ...kTaskColumns};

/// Decodes a `tasks` row. Booleans are 0 or 1, JSON columns are text, `overdue` is derived from
/// [nowUtc] and the names of the owner and assignee are null (they are not stored). Every column
/// outside the built-in set (an adopting app's own) lands in `Task.extras` as the row holds it.
///
/// [mirrorStatusFor] (default null: the stored `mirror_status` is used) is asked for each row. A
/// non-null answer is a `MirrorStatus` wire value (`pending`, `mirrored`, `skipped`, `failed`) that
/// replaces the stored one; null keeps the stored value. An unknown string shows as `pending`. A hook
/// that throws keeps the stored value for that row; the rest of the list still reads. The hook gets the
/// row as stored (local column names).
///
/// [shape] (default: the module's own table) says where each module column lives: a cell is read by its
/// local name, a renamed column never lands in `Task.extras` and an absent column reads as null.
///
/// Tolerant reader: a blank string (empty or only spaces) in `assigned_user_id`, `due_date` or `due_time`, and the empty
/// string in `notes`, reads as null.
/// Only when [shape] is not the default (it has `absent` or `rename` entries, or orders by date then time):
/// a timed row without a due instant gets the device's (`deviceDueAt` of its date and time). The default
/// shape keeps a missing `due_at` as null (existing behaviour).
Task taskFromRow(SyncRow row, {required DateTime nowUtc, MirrorStatusFor? mirrorStatusFor, TaskTableShape shape = const TaskTableShape()}) {
  Object? cell(String c) => shape.has(c) ? row[shape.local(c)] : null;
  final dueDate = _nb(cell('due_date')), dueTime = _nb(cell('due_time'));
  final dueAt = _time(cell('due_at')) ?? (_isShaped(shape) ? _deviceDue(dueDate, dueTime) : null);
  final flag = cell('mirror_enabled');
  final m = <String, Object?>{
    'id': _str(row['id']),
    'title': _str(cell('title')),
    'notes': _empty(cell('notes')),
    'due_date': dueDate,
    'due_time': dueTime,
    'priority': _int(cell('priority')),
    'due_at': dueAt,
    'status': _str(cell('status')),
    'owner_user_id': _str(cell('owner_user_id')),
    'assigned_user_id': _nb(cell('assigned_user_id')),
    'checklist': _list(cell('checklist'), (e) => _ok(e, ChecklistItem.fromJson)),
    'remind_minutes_before': _int(cell('remind_minutes_before')),
    'links': _list(cell('links'), (e) => _ok(e, TaskLink.fromJson)),
    'completed_at': _time(cell('completed_at')),
    'mirror_enabled': flag == null ? null : _int(flag) != 0,
    'mirror_status': _mirror(row, mirrorStatusFor, shape),
    'external_provider': _str(cell('external_provider')),
    'external_event_id': _str(cell('external_event_id')),
    'source': _str(cell('source')),
    'created_at': _time(cell('created_at')),
    'updated_at': _time(cell('updated_at')),
  };
  final renamed = shape.rename.values.toSet();
  for (final e in row.entries) {
    if (!_known.contains(e.key) && !renamed.contains(e.key) && !kTaskItemKeys.contains(e.key)) m[e.key] = e.value;
  }
  final task = Task.fromJson(m);
  return task.copyWith(overdue: isOverdue(task, nowUtc));
}

bool _isShaped(TaskTableShape s) => s.absent.isNotEmpty || s.rename.isNotEmpty || s.dueOrder == TaskDueOrder.dateThenTime;

String? _deviceDue(String? date, String? time) {
  final at = deviceDueAt(date, time);
  return at == null ? null : isoZ(at);
}
