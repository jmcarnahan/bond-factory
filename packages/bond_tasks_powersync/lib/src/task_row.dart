/// A synced `tasks` row to a [Task].
library;

import 'dart:convert';

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_tasks/bond_tasks.dart';

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

String? _str(Object? v) => v?.toString();

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

/// Decodes a `tasks` row. Booleans are 0 or 1, JSON columns are text, `overdue` is derived from
/// [nowUtc] and the names of the owner and assignee are null (they are not stored).
Task taskFromRow(SyncRow row, {required DateTime nowUtc}) {
  final m = <String, Object?>{
    'id': _str(row['id']),
    'title': _str(row['title']),
    'notes': _str(row['notes']),
    'due_date': _str(row['due_date']),
    'due_time': _str(row['due_time']),
    'priority': _int(row['priority']),
    'due_at': _time(row['due_at']),
    'status': _str(row['status']),
    'owner_user_id': _str(row['owner_user_id']),
    'assigned_user_id': _str(row['assigned_user_id']),
    'checklist': _list(row['checklist'], (e) => _ok(e, ChecklistItem.fromJson)),
    'remind_minutes_before': _int(row['remind_minutes_before']),
    'links': _list(row['links'], (e) => _ok(e, TaskLink.fromJson)),
    'completed_at': _time(row['completed_at']),
    'mirror_enabled': row['mirror_enabled'] == null ? null : _int(row['mirror_enabled']) != 0,
    'mirror_status': _str(row['mirror_status']),
    'external_provider': _str(row['external_provider']),
    'external_event_id': _str(row['external_event_id']),
    'source': _str(row['source']),
    'created_at': _time(row['created_at']),
    'updated_at': _time(row['updated_at']),
  };
  final task = Task.fromJson(m);
  return task.copyWith(overdue: isOverdue(task, nowUtc));
}
