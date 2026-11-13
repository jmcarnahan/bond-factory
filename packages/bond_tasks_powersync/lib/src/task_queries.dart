/// SQL text of the task reads, built from the table shape. The default shape gives today's strings.
library;

import 'package:bond_tasks/bond_tasks.dart';

import 'task_table_shape.dart';
import 'tasks_tables.dart';

/// The pieces of read SQL that depend on the table [shape].
class TaskSql {
  const TaskSql(this.shape);

  final TaskTableShape shape;

  /// The local column of a module column.
  String c(String moduleColumn) => shape.local(moduleColumn);

  String get mine => '(${c('owner_user_id')} = ? OR ${c('assigned_user_id')} = ?)';

  String get order {
    final created = c('created_at');
    if (shape.dueOrder == TaskDueOrder.dueAt) return 'ORDER BY ${c('due_at')} IS NULL, ${c('due_at')}, $created DESC, id';
    final d = c('due_date'), t = c('due_time');
    return 'ORDER BY $d IS NULL, $d, $t IS NULL, $t, $created DESC, id';
  }

  /// The SQL and parameters of `list(f)`: the status (default `open`), the mine / owner / assignee / no-date conditions, then the order.
  (String, List<Object?>) listQuery(TaskFilters f, String userId) {
    final where = <String>[];
    final args = <Object?>[];
    final status = f.status ?? 'open';
    if (status == 'open' || status == 'done' || status == 'cancelled') {
      where.add('${c('status')} = ?');
      args.add(status);
    }
    if ((f.scope ?? 'mine') == 'mine') {
      where.add(mine);
      args.addAll([userId, userId]);
    }
    if (f.ownerUserId != null) {
      where.add('${c('owner_user_id')} = ?');
      args.add(f.ownerUserId);
    }
    if (f.assignedUserId != null) {
      where.add('${c('assigned_user_id')} = ?');
      args.add(f.assignedUserId);
    }
    if (f.assignedToMe) {
      where.add('${c('assigned_user_id')} = ?');
      args.add(userId);
    }
    if (f.noDate) where.add('${c('due_date')} IS NULL');
    return ('SELECT * FROM $kTasksTable${where.isEmpty ? '' : ' WHERE ${where.join(' AND ')}'} $order', args);
  }

  /// `WHERE` conditions and parameters for `listWhere`: the [equals] keys (module columns or [extraColumns];
  /// validated before any SQL is built), then (with `mine`) the owner-or-assignee condition, then the status when it is `open`, `done` or `cancelled`.
  (List<String>, List<Object?>) equalsWhere(
    Map<String, Object?> equals,
    Set<String> extraColumns,
    String? status, {
    bool mine = false,
    String? userId,
  }) {
    final module = kTaskColumns.toSet();
    final where = <String>[];
    final args = <Object?>[];
    for (final e in equals.entries) {
      final k = e.key;
      final String col;
      if (module.contains(k)) {
        if (!shape.has(k)) throw ArgumentError.value(k, 'equals', 'is absent from the local table');
        col = c(k);
      } else if (extraColumns.contains(k)) {
        col = k;
      } else {
        throw ArgumentError.value(k, 'equals', 'is not a module column or an extra column');
      }
      final v = e.value;
      if (v == null) {
        where.add('$col IS NULL');
      } else {
        where.add('$col = ?');
        args.add(v is bool ? (v ? 1 : 0) : v);
      }
    }
    if (mine) {
      where.add(this.mine);
      args.addAll([userId, userId]);
    }
    if (status == 'open' || status == 'done' || status == 'cancelled') {
      where.add('${c('status')} = ?');
      args.add(status);
    }
    return (where, args);
  }
}

/// The tasks whose day (see `dayFor`) falls in the filter's `dueFrom` .. earlier of `onOrBefore` / `dueTo` range; all of them
/// when the filter has no range. Undated tasks stay only with `includeUndated`.
List<Task> tasksInRange(List<Task> tasks, TaskFilters f) {
  final hiParts = [if (f.onOrBefore != null) f.onOrBefore!, if (f.dueTo != null) f.dueTo!]..sort();
  final lo = f.dueFrom, hi = hiParts.isEmpty ? null : hiParts.first;
  if (lo == null && hi == null) return tasks;
  bool dayIn(String? day) {
    if (day == null) return f.includeUndated;
    return (lo == null || day.compareTo(lo) >= 0) && (hi == null || day.compareTo(hi) <= 0);
  }

  return [
    for (final t in tasks)
      if (dayIn(dayFor(t, (u) => u.toLocal()))) t,
  ];
}
