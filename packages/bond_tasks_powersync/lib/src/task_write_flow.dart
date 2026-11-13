/// The sequence of one task write inside its transaction: before -> values -> prepare -> mirror status
/// -> statement -> afterWrite.
library;

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_tasks/bond_tasks.dart';

import 'task_hooks.dart';
import 'task_row.dart';
import 'task_table_shape.dart';
import 'task_writes.dart';
import 'tasks_tables.dart';

/// Runs the writes of a `PowerSyncTaskRepository` with its shape and hooks.
class TaskWriter {
  TaskWriter({
    required this.userId,
    required this.clock,
    required this.extraColumns,
    required this.shape,
    required this.writeCompletedBy,
    this.mirrorOnWrite,
    this.prepare,
    this.afterWrite,
  });

  final String userId;
  final TaskClock clock;
  final Set<String> extraColumns;
  final TaskTableShape shape;
  final bool writeCompletedBy;
  final MirrorStatusOnWrite? mirrorOnWrite;
  final TaskPrepare? prepare;
  final TaskAfterWrite? afterWrite;

  Future<String> create(SyncSql tx, TaskDraft d) async {
    final (id, module) = buildInsert(d, userId: userId, nowUtc: clock.nowUtc(), extraColumns: extraColumns);
    var values = localValues(shape, module);
    values = await _prepared(tx, TaskWriteKind.create, id, null, values);
    values = _mirrored(id, null, values);
    await executeInsert(tx, id, values);
    await afterWrite?.call(tx, TaskWrite(kind: TaskWriteKind.create, id: id, values: values));
    return id;
  }

  /// [before] is the stored row. Nothing is written when the patch and `prepare` give no column.
  Future<void> update(SyncSql tx, String id, SyncRow before, TaskPatch p) async {
    final module = patchColumns(before, p, extraColumns: extraColumns, shape: shape);
    var values = localValues(shape, module);
    values = await _prepared(tx, TaskWriteKind.update, id, before, values);
    if (values.isEmpty) return;
    values = {...values, shape.local('updated_at'): isoZ(clock.nowUtc())};
    values = _mirrored(id, before, values);
    await executeUpdate(tx, id, values);
    await afterWrite?.call(tx, TaskWrite(kind: TaskWriteKind.update, id: id, before: before, values: values));
  }

  /// [before] is the stored row; the caller has checked the task is not already in the target status.
  Future<void> status(SyncSql tx, String id, String action, SyncRow before) async {
    var values = statusValues(action, clock.nowUtc(), shape: shape, writeCompletedBy: writeCompletedBy, userId: userId);
    values = _mirrored(id, before, values);
    await executeStatus(tx, id, action, values);
    final kind = TaskWriteKind.values.byName(action);
    await afterWrite?.call(tx, TaskWrite(kind: kind, id: id, before: before, values: values));
  }

  Future<void> delete(SyncSql tx, String id) async {
    final hook = afterWrite;
    final before = hook == null ? null : await tx.getOptional('SELECT * FROM $kTasksTable WHERE id = ?', [id]);
    await tx.execute('DELETE FROM $kTasksTable WHERE id = ?', [id]);
    await hook?.call(tx, TaskWrite(kind: TaskWriteKind.delete, id: id, before: before));
  }

  Future<Map<String, Object?>> _prepared(SyncSql tx, TaskWriteKind kind, String id, SyncRow? before, Map<String, Object?> values) async {
    final hook = prepare;
    if (hook == null) return values;
    final out = {...await hook(tx, TaskWrite(kind: kind, id: id, before: before, values: Map.unmodifiable(values)))};
    final allowed = {
      ...values.keys,
      ...extraColumns,
      for (final c in kTaskColumns)
        if (shape.has(c)) shape.local(c),
    };
    for (final k in out.keys) {
      if (!allowed.contains(k)) throw ArgumentError.value(k, 'prepare', 'is not a column this write may set');
    }
    if (kind == TaskWriteKind.create) {
      for (final c in kRequiredTaskColumns) {
        if (!out.containsKey(shape.local(c))) throw ArgumentError.value(shape.local(c), 'prepare', 'a create must still write this column');
      }
    } else {
      for (final c in const ['status', 'completed_at', 'completed_by']) {
        final k = shape.local(c);
        if (out.containsKey(k) && (!values.containsKey(k) || out[k] != values[k])) {
          throw ArgumentError.value(k, 'prepare', 'an update may not set the status columns: use complete, reopen or cancel');
        }
      }
    }
    return out;
  }

  Map<String, Object?> _mirrored(String id, SyncRow? before, Map<String, Object?> values) {
    final hook = mirrorOnWrite;
    if (hook == null) return values;
    final v = hook({...?before, 'id': id, ...values}, before);
    if (v == null || !shape.has('mirror_status')) return values;
    return {...values, shape.local('mirror_status'): v};
  }
}
