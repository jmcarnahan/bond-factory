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

/// INSERT of a new task; returns its id.
Future<String> insertTask(SyncSql tx, TaskDraft d, {required String userId, required DateTime nowUtc}) async {
  final problems = d.validate();
  if (problems.isNotEmpty) throw ArgumentError('invalid task draft: ${problems.map((p) => p.name).join(', ')}');
  final id = d.id ?? newTaskId();
  if (!kClientId.hasMatch(id)) throw ArgumentError.value(id, 'id', 'must match [A-Za-z0-9_-]{1,64}');
  final timed = d.dueDate != null && d.dueDate!.isNotEmpty && d.dueTime != null && d.dueTime!.isNotEmpty;
  final dueAt = timed ? (d.dueAt ?? deviceDueAt(d.dueDate, d.dueTime)) : null;
  final now = isoZ(nowUtc);
  final values = <String, Object?>{
    'id': id,
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
  };
  final cols = values.keys.toList();
  await tx.execute(
    'INSERT INTO $kTasksTable (${cols.join(', ')}) VALUES (${List.filled(cols.length, '?').join(', ')})',
    [for (final c in cols) values[c]],
  );
  return id;
}

String? _blank(String? s) => s == null || s.isEmpty ? null : s;

/// The columns a [patch] changes, in a fixed order, given the stored [row]; empty when nothing changes.
Map<String, Object?> patchColumns(SyncRow row, TaskPatch p) {
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
  final oldDate = _blank(row['due_date'] as String?), oldTime = _blank(row['due_time'] as String?);
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
  return set;
}

/// UPDATE of only [set] plus `updated_at`; no statement when [set] is empty.
Future<void> updateColumns(SyncSql tx, String id, Map<String, Object?> set, DateTime nowUtc) async {
  if (set.isEmpty) return;
  final all = {...set, 'updated_at': isoZ(nowUtc)};
  await tx.execute(
    'UPDATE $kTasksTable SET ${all.keys.map((c) => '$c = ?').join(', ')} WHERE id = ?',
    [...all.values, id],
  );
}

/// UPDATE for complete (`done`), reopen (`open`) and cancel (`cancelled`).
Future<void> setStatus(SyncSql tx, String id, String action, DateTime nowUtc) async {
  final (status, completed) = switch (action) {
    'complete' => ('done', isoZ(nowUtc)),
    'reopen' => ('open', null),
    _ => ('cancelled', null),
  };
  await tx.execute(
    'UPDATE $kTasksTable SET status = ?, completed_at = ?, updated_at = ?, _metadata = ? WHERE id = ?',
    [status, completed, isoZ(nowUtc), jsonEncode({'action': action}), id],
  );
}
