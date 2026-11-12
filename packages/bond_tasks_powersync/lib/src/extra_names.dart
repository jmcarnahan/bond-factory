/// Name checks shared by `tasksTables` and `PowerSyncTaskRepository`.
library;

import 'package:bond_tasks/bond_tasks.dart' show kTaskItemKeys;

import 'tasks_tables.dart';

final RegExp _safeName = RegExp(r'^[a-z_][a-z0-9_]*$');

/// The names of the indexes the package defines itself.
const Set<String> kBuiltInIndexNames = {'owner_status', 'assignee_status', 'status_due'};

Set<String> get _reserved => {
      'id',
      '_metadata',
      for (final c in kTaskColumns) c.toLowerCase(),
      for (final k in kTaskItemKeys) k.toLowerCase(),
    };

/// Throws [ArgumentError] when a name is not a plain lower-case column name, is a built-in column,
/// `id`, `_metadata` or a `TaskItem` key, or is listed twice. The name goes into SQL, so it must be safe.
void checkExtraColumnNames(Iterable<String> names, [String argument = 'extraColumns']) {
  final reserved = _reserved;
  final seen = <String>{};
  for (final n in names) {
    if (!_safeName.hasMatch(n)) {
      throw ArgumentError.value(n, argument, 'must match ^[a-z_][a-z0-9_]*\$');
    }
    if (reserved.contains(n.toLowerCase())) throw ArgumentError.value(n, argument, 'clashes with a built-in column');
    if (!seen.add(n)) throw ArgumentError.value(n, argument, 'listed twice');
  }
}

/// Throws [ArgumentError] when an index name repeats a built-in index name or another extra one.
void checkExtraIndexNames(Iterable<String> names) {
  final seen = <String>{};
  for (final n in names) {
    final k = n.toLowerCase();
    if (kBuiltInIndexNames.contains(k)) throw ArgumentError.value(n, 'extraIndexes', 'clashes with a built-in index');
    if (!seen.add(k)) throw ArgumentError.value(n, 'extraIndexes', 'listed twice');
  }
}
