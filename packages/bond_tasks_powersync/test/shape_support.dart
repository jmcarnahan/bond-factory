import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_sync_powersync/testing.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';

/// A phone table that already exists: no priority, due instant, checklist, reminder, links or calendar ids; the
/// mirror flag is `sync_to_calendar`; the app's own columns are client_ref, case_ref and case_file_no.
const legacyShape = TaskTableShape(
  absent: {
    'priority',
    'due_at',
    'checklist',
    'remind_minutes_before',
    'links',
    'external_provider',
    'external_event_id',
    'external_account_user_id',
    'external_etag',
  },
  rename: {'mirror_enabled': 'sync_to_calendar'},
);

const legacyExtras = {'client_ref', 'case_ref', 'case_file_no'};

Set<String> legacyColumns() => {
      'id',
      '_metadata',
      for (final c in kTaskColumns)
        if (legacyShape.has(c)) legacyShape.local(c),
      ...legacyExtras,
    };

/// A stored legacy row (every column present, null unless given).
SyncRow legacyRow(String id, [Map<String, Object?> v = const {}]) => {
      for (final c in legacyColumns()) c: null,
      'id': id,
      'owner_user_id': 'user-1',
      'title': 'T $id',
      'status': 'open',
      'sync_to_calendar': 1,
      'mirror_status': 'pending',
      'created_at': '2026-03-01T00:00:00.000Z',
      'updated_at': '2026-03-01T00:00:00.000Z',
      ...v,
    };

FakeSyncDb legacyDb(List<SyncRow> rows, {Map<String, List<SyncRow>> more = const {}, Map<String, Set<String>> moreColumns = const {}}) =>
    FakeSyncDb.tables({'tasks': rows, ...more}, applySql: true, columns: {'tasks': legacyColumns(), ...moreColumns});

final DateTime t0 = DateTime.utc(2026, 3, 11, 20);

PowerSyncTaskRepository legacyRepo(
  FakeSyncDb db, {
  DateTime? now,
  TaskTableShape shape = legacyShape,
  Set<String> extraColumns = legacyExtras,
  bool writeCompletedBy = false,
  MirrorStatusOnWrite? mirrorStatusOnWrite,
  TaskPrepare? prepare,
  TaskAfterWrite? afterWrite,
  TaskEnricher? enricher,
  List<String> extraWatchTables = const [],
}) =>
    PowerSyncTaskRepository(
      db,
      userId: 'user-1',
      clock: TaskClock(() => now ?? t0),
      shape: shape,
      extraColumns: extraColumns,
      writeCompletedBy: writeCompletedBy,
      mirrorStatusOnWrite: mirrorStatusOnWrite,
      prepare: prepare,
      afterWrite: afterWrite,
      enricher: enricher,
      extraWatchTables: extraWatchTables,
    );
