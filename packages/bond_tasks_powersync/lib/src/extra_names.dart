/// Name checks shared by `tasksTables` and `PowerSyncTaskRepository`.
library;

import 'package:bond_tasks/bond_tasks.dart' show kTaskItemKeys;

import 'tasks_tables.dart';

final RegExp _safeName = RegExp(r'^[a-z_][a-z0-9_]*$');

/// Names SQLite refuses as an unquoted column name (checked against SQLite 3.51 through CREATE TABLE, INSERT, UPDATE, SELECT ... WHERE
/// ... ORDER BY and CREATE INDEX). The SQL here never quotes a name, so such a column never worked. Words SQLite accepts unquoted
/// (`key`, `end`, `by`, `offset`, `column`, `like`, ...) are NOT listed.
const Set<String> kSqliteKeywords = {
  'add', 'all', 'alter', 'and', 'as', 'between', 'case', 'cast', 'check', 'collate', 'commit', 'create', 'default', 'delete',
  'distinct', 'drop', 'else', 'escape', 'except', 'exists', 'from', 'group', 'having', 'in', 'index', 'insert', 'into', 'is',
  'isnull', 'join', 'limit', 'not', 'nothing', 'notnull', 'null', 'on', 'or', 'order', 'primary', 'references', 'returning',
  'select', 'set', 'table', 'then', 'to', 'transaction', 'union', 'unique', 'update', 'using', 'values', 'when', 'where', //
};

/// The names of the indexes the package defines itself.
const Set<String> kBuiltInIndexNames = {'owner_status', 'assignee_status', 'status_due'};

Set<String> get _reserved => {
      'id',
      '_metadata',
      for (final c in kTaskColumns) c.toLowerCase(),
      for (final k in kTaskItemKeys) k.toLowerCase(),
    };

/// Throws [ArgumentError] when a name is not a plain lower-case column name, is an SQL keyword, is a built-in column,
/// `id`, `_metadata` or a `TaskItem` key, or is listed twice. The name goes into SQL, so it must be safe.
void checkExtraColumnNames(Iterable<String> names, [String argument = 'extraColumns']) {
  final reserved = _reserved;
  final seen = <String>{};
  for (final n in names) {
    if (!_safeName.hasMatch(n)) {
      throw ArgumentError.value(n, argument, 'must match ^[a-z_][a-z0-9_]*\$');
    }
    if (kSqliteKeywords.contains(n.toLowerCase())) throw ArgumentError.value(n, argument, 'is an SQL keyword');
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
