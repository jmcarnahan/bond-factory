@Tags(['real_db'])
@TestOn('vm')
library;

import 'dart:io';

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:powersync/powersync.dart';

import 'shape_support.dart';

/// The repository at the legacy shape against a REAL local PowerSync database whose `tasks` table is declared by hand
/// (not `tasksTables()`): the queued CRUD entries carry exactly the legacy columns that were written.
final _legacyTable = Table(
  'tasks',
  [
    for (final c in ['owner_user_id', 'created_by', 'assigned_user_id', 'title', 'notes', 'due_date', 'due_time', 'status', 'completed_at'])
      Column.text(c),
    for (final c in ['completed_by', 'mirror_status', 'source', 'created_at', 'updated_at', 'client_ref', 'case_ref', 'case_file_no']) Column.text(c),
    const Column.integer('sync_to_calendar'),
  ],
  trackMetadata: true,
);
final _schema = Schema([_legacyTable, ...syncSupportTables()]);
var now = DateTime.utc(2026, 3, 11, 20);

Future<List<SyncCrudEntry>> drain(SyncDb db) async {
  final out = <SyncCrudEntry>[];
  while (true) {
    final tx = await db.nextCrudTransaction();
    if (tx == null) return out;
    out.addAll(tx.entries);
    await tx.complete();
  }
}

void main() {
  late Directory dir;
  late PowerSyncDatabase raw;
  late SyncDb db;

  PowerSyncTaskRepository repo({TaskAfterWrite? afterWrite}) => PowerSyncTaskRepository(
        db,
        userId: 'user-1',
        clock: TaskClock(() => now),
        shape: legacyShape,
        extraColumns: legacyExtras,
        writeCompletedBy: true,
        afterWrite: afterWrite,
      );

  setUp(() async {
    now = DateTime.utc(2026, 3, 11, 20);
    dir = Directory.systemTemp.createTempSync('btp_shape_real');
    raw = PowerSyncDatabase(schema: _schema, path: '${dir.path}/t.db');
    await raw.initialize();
    db = PowerSyncDb(raw);
  });

  tearDown(() async {
    await raw.close();
    dir.deleteSync(recursive: true);
  });

  test('create, update, complete, reopen, delete queue exactly the legacy columns written', () async {
    final r = repo();
    final created = await r.create(const TaskDraft(
      title: 'Legacy',
      id: 't1',
      dueDate: '2026-03-13',
      dueTime: '14:00',
      priority: TaskPriority.high, // no such column: dropped
      extras: {'client_ref': 'C1', 'case_ref': 'K1'},
    ));
    expect(created.dueAt, deviceDueAt('2026-03-13', '14:00'));
    expect((created.priority, created.mirrorEnabled, created.extras['client_ref']), (null, true, 'C1'));

    final put = (await drain(db)).single;
    expect((put.op, put.table, put.id), ('put', 'tasks', 't1'));
    final legacy = {...legacyColumns()}..removeAll({'id', '_metadata'});
    expect(put.opData!.keys.toSet().difference(legacy), isEmpty, reason: 'only legacy columns');
    expect(put.opData!.keys.toSet(), {
      'owner_user_id', 'created_by', 'title', 'due_date', 'due_time', 'status', 'sync_to_calendar', 'mirror_status', 'source',
      'created_at', 'updated_at', 'client_ref', 'case_ref', //
    });
    expect(put.opData!['sync_to_calendar'], 1);
    expect(put.opData!['mirror_status'], 'pending');

    now = now.add(const Duration(minutes: 1)); // PowerSync records only columns whose value changed
    await r.update('t1', const TaskPatch(title: 'Legacy 2', mirrorEnabled: false, extras: {'client_ref': 'C2'}));
    final patch = (await drain(db)).single;
    expect(patch.op, 'patch');
    expect(patch.opData!.keys.toSet(), {'title', 'sync_to_calendar', 'client_ref', 'updated_at'});
    expect(patch.opData!['sync_to_calendar'], 0);

    now = now.add(const Duration(minutes: 1));
    final done = await r.complete('t1');
    expect(done.status, TaskStatus.done);
    final complete = (await drain(db)).single;
    expect(complete.opData!.keys.toSet(), {'status', 'completed_at', 'completed_by', 'updated_at'});
    expect(complete.opData!['completed_by'], 'user-1');
    expect(complete.metadata, '{"action":"complete"}');

    now = now.add(const Duration(minutes: 1));
    await r.reopen('t1');
    final reopen = (await drain(db)).single;
    expect(reopen.opData!.keys.toSet(), {'status', 'completed_at', 'completed_by', 'updated_at'});
    expect(reopen.opData!['completed_by'], isNull);
    expect(reopen.metadata, '{"action":"reopen"}');

    final read = await r.getTask('t1');
    expect((read!.title, read.mirrorEnabled, read.status), ('Legacy 2', false, TaskStatus.open));
    final page = await r.listWhere({'client_ref': 'C2'}, status: 'open');
    expect((page.total, page.items.single.id), (1, 't1'));

    now = now.add(const Duration(minutes: 1));
    await r.delete('t1');
    expect((await drain(db)).single.op, 'delete');
    expect(await r.getTask('t1'), isNull);
  });

  test('a throw from afterWrite rolls the whole write back: no row, nothing queued', () async {
    final r = repo(afterWrite: (tx, w) async => throw StateError('rule'));
    await expectLater(r.create(const TaskDraft(title: 'X', id: 'x1')), throwsStateError);
    expect(await repo().getTask('x1'), isNull);
    expect(await drain(db), isEmpty);
  });

  test('afterWrite throwing on update and on complete, and prepare throwing on create, roll back: row unchanged, queue empty', () async {
    await repo().create(const TaskDraft(title: 'Keep', id: 'k1', extras: {'client_ref': 'C1'}));
    await drain(db);
    now = now.add(const Duration(minutes: 1));
    final boom = repo(afterWrite: (tx, w) async => throw StateError('rule'));
    await expectLater(boom.update('k1', const TaskPatch(title: 'Changed')), throwsStateError);
    await expectLater(boom.complete('k1'), throwsStateError);
    final row = await repo().getTask('k1');
    expect((row!.title, row.status, row.completedAt), ('Keep', TaskStatus.open, null));
    expect(await drain(db), isEmpty);
    final prep = PowerSyncTaskRepository(
      db,
      userId: 'user-1',
      clock: TaskClock(() => now),
      shape: legacyShape,
      extraColumns: legacyExtras,
      prepare: (tx, w) async => throw StateError('prepare'),
    );
    await expectLater(prep.create(const TaskDraft(title: 'No', id: 'p1')), throwsStateError);
    expect(await repo().getTask('p1'), isNull);
    expect(await drain(db), isEmpty);
  });
}
