/// How the local `tasks` table differs from the module's own.
library;

import 'extra_names.dart';
import 'tasks_tables.dart';

/// The order of open tasks: by the due instant, or by the date and time columns.
enum TaskDueOrder {
  /// `ORDER BY due_at IS NULL, due_at, created_at DESC, id` (today's order).
  dueAt,

  /// `ORDER BY due_date IS NULL, due_date, due_time IS NULL, due_time, created_at DESC, id`: for a table
  /// without a (reliable) due instant.
  dateThenTime,
}

final RegExp _safeName = RegExp(r'^[a-z_][a-z0-9_]*$');

/// Columns a local table must always have: the repository's rules read or write them.
const Set<String> kRequiredTaskColumns = {
  'owner_user_id',
  'assigned_user_id',
  'title',
  'status',
  'due_date',
  'due_time',
  'completed_at',
  'created_at',
  'updated_at',
};

/// How an existing local `tasks` table (one a phone build already shipped) differs from the module's
/// table, for `PowerSyncTaskRepository(shape:)`. The default shape is the module's own table: every
/// SQL string stays as it is today.
///
/// Names in [absent] and the keys of [rename] are module column names (see `kTaskColumns`). SQL built
/// from a shape never names an absent column: a draft or patch value for one is dropped silently and a
/// read gives null. The repository constructor calls [check].
class TaskTableShape {
  const TaskTableShape({this.absent = const {}, this.rename = const {}, TaskDueOrder? dueOrder}) : _dueOrder = dueOrder;

  /// Module columns the local table does not declare.
  final Set<String> absent;

  /// Module column name to the local column that holds it.
  final Map<String, String> rename;
  final TaskDueOrder? _dueOrder;

  /// The given order, else [TaskDueOrder.dateThenTime] when `due_at` is absent, else [TaskDueOrder.dueAt].
  TaskDueOrder get dueOrder => _dueOrder ?? (absent.contains('due_at') ? TaskDueOrder.dateThenTime : TaskDueOrder.dueAt);

  /// The local column holding [moduleColumn] (the same name unless renamed).
  String local(String moduleColumn) => rename[moduleColumn] ?? moduleColumn;

  /// False when the local table does not declare [moduleColumn].
  bool has(String moduleColumn) => !absent.contains(moduleColumn);

  /// Throws [ArgumentError] when the shape cannot work: an unknown module column in [absent] or [rename]; an
  /// absent column the rules need (`owner_user_id`, `assigned_user_id`, `title`, `status`, `due_date`,
  /// `due_time`, `completed_at`, `created_at`, `updated_at`); a renamed column also listed absent; a local
  /// name that is unsafe (`^[a-z_][a-z0-9_]*$`), is an SQL keyword, is `id`, `_metadata`, another module column, one of
  /// [extraColumns] or used twice; `dueOrder: dueAt` with `due_at` absent.
  void check(Set<String> extraColumns) {
    final module = kTaskColumns.toSet();
    for (final c in absent) {
      if (!module.contains(c)) throw ArgumentError.value(c, 'shape.absent', 'is not a module column');
      if (kRequiredTaskColumns.contains(c)) throw ArgumentError.value(c, 'shape.absent', 'cannot be absent');
    }
    final seen = <String>{};
    for (final e in rename.entries) {
      if (!module.contains(e.key)) throw ArgumentError.value(e.key, 'shape.rename', 'is not a module column');
      if (absent.contains(e.key)) throw ArgumentError.value(e.key, 'shape.rename', 'is also listed absent');
      final n = e.value;
      if (!_safeName.hasMatch(n)) throw ArgumentError.value(n, 'shape.rename', 'must match ^[a-z_][a-z0-9_]*\$');
      if (n == 'id' || n == '_metadata') throw ArgumentError.value(n, 'shape.rename', 'is reserved');
      if (kSqliteKeywords.contains(n)) throw ArgumentError.value(n, 'shape.rename', 'is an SQL keyword');
      if (n != e.key && module.contains(n)) throw ArgumentError.value(n, 'shape.rename', 'is another module column');
      if (extraColumns.contains(n)) throw ArgumentError.value(n, 'shape.rename', 'is also an extra column');
      if (!seen.add(n)) throw ArgumentError.value(n, 'shape.rename', 'used twice');
    }
    if (_dueOrder == TaskDueOrder.dueAt && absent.contains('due_at')) {
      throw ArgumentError.value(TaskDueOrder.dueAt, 'shape.dueOrder', 'needs due_at, which is absent');
    }
  }
}

/// A copy of [s] whose collections can no longer be changed through the caller's references.
TaskTableShape copyShape(TaskTableShape s) =>
    TaskTableShape(absent: Set.unmodifiable(s.absent), rename: Map.unmodifiable(s.rename), dueOrder: s.dueOrder);
