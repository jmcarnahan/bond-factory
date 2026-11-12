@Tags(['real_db'])
@TestOn('vm')
library;

import 'dart:io';

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:powersync/powersync.dart';

/// The repository against a REAL local PowerSync database (no sync service): reads go through the real views,
/// writes land in the real CRUD queue, which is asserted here.
final _schema = Schema([...tasksTables(), ...syncSupportTables()]);
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
  late PowerSyncTaskRepository repo;

  setUp(() async {
    now = DateTime.utc(2026, 3, 11, 20);
    dir = Directory.systemTemp.createTempSync('btp_real');
    raw = PowerSyncDatabase(schema: _schema, path: '${dir.path}/t.db');
    await raw.initialize();
    db = PowerSyncDb(raw);
    repo = PowerSyncTaskRepository(db, userId: 'user-1', clock: TaskClock(() => now));
  });

  tearDown(() async {
    await raw.close();
    dir.deleteSync(recursive: true);
  });

  test('create, update, complete and cancel: reads and the queued CRUD entries', () async {
    final seen = <List<String>>[];
    final sub = repo.watchOpen().listen((l) => seen.add([for (final t in l) t.id]));
    final timed = await repo.create(const TaskDraft(title: 'Timed', id: 't1', dueDate: '2026-03-13', dueTime: '14:00'));
    final dated = await repo.create(const TaskDraft(title: 'Dated', id: 't2', dueDate: '2026-03-11', priority: TaskPriority.high));
    await Future<void>.delayed(const Duration(milliseconds: 150)); // let the throttled watch deliver both
    expect(timed.dueAt, deviceDueAt('2026-03-13', '14:00'));
    expect(dated.dueAt, isNull);

    now = now.add(const Duration(minutes: 1)); // PowerSync records only columns whose value changed
    await repo.update('t1', const TaskPatch(title: 'Timed again', notes: Present('n')));
    now = now.add(const Duration(minutes: 1));
    final done = await repo.complete('t1');
    expect(done.status, TaskStatus.done);
    expect(done.completedAt, now);
    now = now.add(const Duration(minutes: 1));
    final cancelled = await repo.cancel('t2');
    expect(cancelled.status, TaskStatus.cancelled);
    await Future<void>.delayed(const Duration(milliseconds: 150));
    await sub.cancel();

    expect(seen.first, anyOf(isEmpty, ['t1'], ['t1', 't2'], ['t2', 't1']));
    expect(seen.last, isEmpty, reason: 'both tasks left the open list');
    expect(seen.any((l) => l.length == 2), isTrue);

    final entries = await drain(db);
    expect(entries.map((e) => (e.op, e.table, e.id)), [
      ('put', 'tasks', 't1'),
      ('put', 'tasks', 't2'),
      ('patch', 'tasks', 't1'),
      ('patch', 'tasks', 't1'),
      ('patch', 'tasks', 't2'),
    ]);
    expect(entries[0].opData!['title'], 'Timed');
    expect(entries[0].opData!['due_at'], isNotNull);
    expect(entries[0].opData!['mirror_enabled'], 1);
    expect(entries[0].opData!['source'], 'manual');
    expect(entries[0].opData!['status'], 'open');
    expect(entries[1].opData!['due_at'], isNull);
    expect(entries[1].opData!['priority'], 3);
    expect(entries[2].opData!.keys.toSet(), {'title', 'notes', 'updated_at'});
    expect(entries[2].metadata, isNull);
    expect(entries[3].opData!.keys.toSet(), {'status', 'completed_at', 'updated_at'});
    expect(entries[3].opData!['status'], 'done');
    expect(entries[3].metadata, '{"action":"complete"}');
    expect(entries[4].opData!['status'], 'cancelled');
    expect(entries[4].metadata, '{"action":"cancel"}');
  });

  test('today() and summary() read through the real views', () async {
    await repo.create(const TaskDraft(title: 'Late', id: 'a', dueDate: '2026-03-01', dueTime: '09:00'));
    await repo.create(const TaskDraft(title: 'Someday', id: 'b'));
    await repo.create(const TaskDraft(title: 'Soon', id: 'c', dueDate: '2026-03-30'));
    await repo.complete('c');
    final s = await repo.summary();
    expect((s.open, s.overdue, s.noDate), (2, 1, 1));
    final t = await repo.today();
    expect(t.overdue.map((x) => x.id), ['a']);
    expect(t.undated.map((x) => x.id), ['b']);
    expect(t.counts.today, 0);
    expect((await repo.list(const TaskFilters(status: 'all'))).total, 3);
    // a timed task edited to date-only queues due_at null (it was a device instant), never a new instant
    await repo.create(const TaskDraft(title: 'Timed', id: 'tt', dueDate: '2026-04-02', dueTime: '10:00'));
    await drain(db);
    now = now.add(const Duration(minutes: 1));
    await repo.update('tt', TaskPatch(dueTime: const Present(null), dueAt: Present(DateTime.utc(2026, 4, 2, 21))));
    final dateOnly = (await drain(db)).single;
    expect(dateOnly.opData!.containsKey('due_at'), isTrue);
    expect(dateOnly.opData!['due_at'], isNull);
    expect(dateOnly.opData!['due_time'], isNull);
    // completing a done task again and reopening an open one queue nothing
    await drain(db);
    now = now.add(const Duration(minutes: 5));
    await repo.complete('c');
    await repo.reopen('a');
    expect(await drain(db), isEmpty);
    // clearing only the date clears the time and the due instant in the real store too
    await repo.update('a', const TaskPatch(dueDate: Present(null)));
    final cleared = await repo.list(const TaskFilters(status: 'all', scope: 'mine', limit: 50));
    final a = cleared.items.firstWhere((x) => x.id == 'a');
    expect((a.dueDate, a.dueTime, a.dueAt), (null, null, null));
    final patch = (await drain(db)).single;
    expect(patch.opData!.keys.toSet(), containsAll({'due_date', 'due_time', 'due_at'}));
    await repo.delete('b');
    expect((await drain(db)).last.op, 'delete');
    expect((await repo.summary()).open, 2); // a and tt
  });
}
