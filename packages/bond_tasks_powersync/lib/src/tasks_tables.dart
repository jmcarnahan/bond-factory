/// The PowerSync table definition of the synced tasks.
library;

import 'package:powersync/powersync.dart';

import 'extra_names.dart';

/// The name of the synced tasks table.
const kTasksTable = 'tasks';

/// Every stored column of a task, text unless listed in [kTaskIntColumns]. `owner_name` and
/// `assignee_name` are not stored: they stay null on the decoded task.
const List<String> kTaskColumns = [
  'owner_user_id',
  'created_by',
  'assigned_user_id',
  'title',
  'notes',
  'due_date',
  'due_time',
  'priority',
  'due_at',
  'status',
  'completed_at',
  'completed_by',
  'checklist',
  'remind_minutes_before',
  'mirror_enabled',
  'mirror_status',
  'external_provider',
  'external_event_id',
  'external_account_user_id',
  'external_etag',
  'links',
  'source',
  'created_at',
  'updated_at',
];

/// The integer columns (booleans are 0 or 1).
const Set<String> kTaskIntColumns = {'priority', 'remind_minutes_before', 'mirror_enabled'};

/// The tables this package reads; add them to the app schema. The table tracks write metadata so
/// a complete, reopen or cancel can name its sync action (`{"action": "complete"}`).
///
/// [extraColumns] are an adopting app's own columns and [extraIndexes] its own indexes. A column
/// name must match `^[a-z_][a-z0-9_]*$` and not be a built-in column, `id`, `_metadata` or a
/// `TaskItem` key; an index name must not repeat a built-in one. Otherwise [ArgumentError].
List<Table> tasksTables({List<Column> extraColumns = const [], List<Index> extraIndexes = const []}) {
  checkExtraColumnNames([for (final c in extraColumns) c.name]);
  checkExtraIndexNames([for (final i in extraIndexes) i.name]);
  return [
    Table(
      kTasksTable,
      [
        for (final c in kTaskColumns) kTaskIntColumns.contains(c) ? Column.integer(c) : Column.text(c),
        ...extraColumns,
      ],
      indexes: [
        const Index('owner_status', [IndexedColumn('owner_user_id'), IndexedColumn('status')]),
        const Index('assignee_status', [IndexedColumn('assigned_user_id'), IndexedColumn('status')]),
        const Index('status_due', [IndexedColumn('status'), IndexedColumn('due_at')]),
        ...extraIndexes,
      ],
      trackMetadata: true,
    ),
  ];
}
