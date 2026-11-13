/// The local schema of an app that already ships a task screen, as it declares it. Not `tasksTables()`.
///
/// Stage [LegacyStage.asShipped]: the `tasks` table the app has today. It lacks nine columns the SDK knows, keeps the
/// calendar flag in `sync_to_calendar` (0/1, NULL meaning on) and has the app's own `client_ref`, `case_ref` and
/// `case_file_no`. Stage [LegacyStage.widened]: the same table after the app adds the nine missing columns to its
/// schema (PowerSync schemas are declarative: open the SAME database file with the new schema; old rows read NULL).
library;

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:powersync/powersync.dart';

enum LegacyStage { asShipped, widened }

/// The nine SDK columns the app's table lacks until [LegacyStage.widened].
const List<String> kMissingColumns = [
  'priority',
  'due_at',
  'checklist',
  'remind_minutes_before',
  'links',
  'external_provider',
  'external_event_id',
  'external_account_user_id',
  'external_etag',
];

const List<String> _text = [
  'owner_user_id', 'created_by', 'assigned_user_id', 'client_ref', 'case_ref', 'title', 'notes', 'due_date', 'due_time',
  'status', 'completed_at', 'completed_by', 'mirror_status', 'source', 'created_at', 'updated_at', //
];

Schema legacySchema(LegacyStage stage) => Schema([
      Table(
        'tasks',
        [
          for (final c in _text) Column.text(c),
          const Column.integer('case_file_no'),
          const Column.integer('sync_to_calendar'),
          if (stage == LegacyStage.widened) ...[
            for (final c in kMissingColumns)
              if (c == 'priority' || c == 'remind_minutes_before') Column.integer(c) else Column.text(c),
          ],
        ],
        indexes: [
          const Index('tasks_owner', [IndexedColumn('owner_user_id'), IndexedColumn('status'), IndexedColumn('due_date')]),
          const Index('tasks_assignee', [IndexedColumn('assigned_user_id'), IndexedColumn('status')]),
          const Index('tasks_client', [IndexedColumn('client_ref')]),
          const Index('tasks_case', [IndexedColumn('case_ref')]),
        ],
        trackMetadata: true,
      ),
      const Table('users', [Column.text('name'), Column.text('email')]),
      const Table('clients', [Column.text('first_name'), Column.text('last_name')]),
      const Table('cases', [Column.text('client_id'), Column.text('label'), Column.integer('file_no')]),
      ...syncSupportTables(),
    ]);
