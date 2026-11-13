import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_sync_powersync/testing.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';

import 'shape_support.dart';
import 'support.dart';

const dateOrder = 'ORDER BY due_date IS NULL, due_date, due_time IS NULL, due_time, created_at DESC, id';
const dueAtOrder = 'ORDER BY due_at IS NULL, due_at, created_at DESC, id';

Future<void> tick() => Future<void>.delayed(Duration.zero);

void main() {
  group('decoding under a shape', () {
    test('cells are read by module name; a renamed column is not an extra; NULL flag is on; absent reads null', () {
      final t = taskFromRow(
        legacyRow('a', {'sync_to_calendar': 0, 'client_ref': 'C1', 'case_ref': null, 'notes': 'n', 'source': 'import'}),
        nowUtc: t0,
        shape: legacyShape,
      );
      expect(t.mirrorEnabled, isFalse);
      expect(t.extras.keys.toSet(), legacyExtras);
      expect(t.extras['client_ref'], 'C1');
      expect(t.extras.containsKey('sync_to_calendar'), isFalse);
      expect((t.priority, t.dueAt, t.remindMinutesBefore, t.externalProvider), (null, null, kRemindNone, null));
      expect(t.checklist, isEmpty);
      expect(t.links, isEmpty);
      expect((t.notes, t.source, t.title), ('n', 'import', 'T a'));
      final on = taskFromRow(legacyRow('b', {'sync_to_calendar': null}), nowUtc: t0, shape: legacyShape);
      expect(on.mirrorEnabled, isTrue);
    });

    test('mirrorStatusFor gets the row as stored (local names)', () {
      SyncRow? seen;
      taskFromRow(legacyRow('a', {'sync_to_calendar': 0}), nowUtc: t0, shape: legacyShape, mirrorStatusFor: (r) {
        seen = r;
        return 'mirrored';
      });
      expect(seen!.containsKey('sync_to_calendar'), isTrue);
      expect(seen!.containsKey('mirror_enabled'), isFalse);
    });

    test('a timed row without due_at gets a device due instant and is overdue by time', () {
      final late = taskFromRow(legacyRow('a', {'due_date': '2026-03-01', 'due_time': '09:00'}), nowUtc: t0, shape: legacyShape);
      expect(late.dueAt, deviceDueAt('2026-03-01', '09:00'));
      expect(late.overdue, isTrue);
      final later = taskFromRow(legacyRow('b', {'due_date': '2026-03-30', 'due_time': '09:00'}), nowUtc: t0, shape: legacyShape);
      expect(later.dueAt, deviceDueAt('2026-03-30', '09:00'));
      expect(later.overdue, isFalse);
      final dateOnly = taskFromRow(legacyRow('c', {'due_date': '2026-03-30'}), nowUtc: t0, shape: legacyShape);
      expect(dateOnly.dueAt, isNull);
    });

    test('a stored due_at still wins over the derived one', () {
      final row = {...rowOf(fixture('task_timed.json')), 'due_at': '2026-03-12T01:00:00.000Z'};
      final t = taskFromRow(row, nowUtc: t0, shape: const TaskTableShape(dueOrder: TaskDueOrder.dateThenTime));
      expect(t.dueAt, DateTime.utc(2026, 3, 12, 1));
    });

    test('blank cells read as null, under any shape', () {
      final blanks = {'assigned_user_id': '', 'notes': '', 'due_date': '', 'due_time': ''};
      for (final shape in [legacyShape, const TaskTableShape()]) {
        final t = taskFromRow(legacyRow('a', blanks), nowUtc: t0, shape: shape);
        expect((t.assignedUserId, t.notes, t.dueDate, t.dueTime), (null, null, null, null));
      }
      final t = taskFromRow({...rowOf(fixture('task_timed.json')), 'notes': '', 'assigned_user_id': ' '}, nowUtc: t0);
      expect((t.notes, t.assignedUserId), (null, null));
    });
  });

  group('order', () {
    final rows = [
      // r1: due instant late, date mid. r2: instant latest, date earliest. r3: no instant, date between.
      legacyRow('r1', {'due_date': '2026-03-20', 'due_at': '2026-03-21T07:00:00.000Z'}),
      legacyRow('r2', {'due_date': '2026-03-12', 'due_time': '10:00', 'due_at': '2026-03-25T00:00:00.000Z'}),
      legacyRow('r3', {'due_date': '2026-03-15'}),
      legacyRow('r4'),
    ];
    final full = {...legacyColumns(), ...taskColumnNames()};

    FakeSyncDbX fullDb() => FakeSyncDbX(rows, full);

    test('dateThenTime sorts by date and time, undated last; the text is exact', () async {
      final db = fullDb().db;
      const shape = TaskTableShape(dueOrder: TaskDueOrder.dateThenTime);
      final repo = PowerSyncTaskRepository(db, userId: 'user-1', clock: TaskClock(() => t0), shape: shape, extraColumns: legacyExtras);
      final open = await repo.watchOpen().first;
      expect(open.map((t) => t.id), ['r2', 'r3', 'r1', 'r4']);
      expect(db.where('ORDER BY').single.sql, "SELECT * FROM tasks WHERE status = 'open' AND (owner_user_id = ? OR assigned_user_id = ?) $dateOrder");
    });

    test('dueAt (the default) sorts by the instant, undated last; the text is exact', () async {
      final db = fullDb().db;
      final repo = PowerSyncTaskRepository(db, userId: 'user-1', clock: TaskClock(() => t0), extraColumns: legacyExtras);
      final open = await repo.watchOpen().first;
      expect(open.map((t) => t.id), ['r1', 'r2', 'r3', 'r4']);
      expect(db.where('ORDER BY').single.sql, "SELECT * FROM tasks WHERE status = 'open' AND (owner_user_id = ? OR assigned_user_id = ?) $dueAtOrder");
    });

    test('today, summary and list use the same order text, and never name an absent column', () async {
      final db = legacyDb(rows);
      final repo = legacyRepo(db);
      await repo.today();
      await repo.summary();
      await repo.list(const TaskFilters(status: 'all'));
      final ordered = db.where('ORDER BY');
      expect(ordered, hasLength(4)); // today: done + open, summary, list
      for (final s in ordered) {
        expect(s.sql, endsWith(dateOrder));
      }
      for (final s in db.statements) {
        expect(s.sql, isNot(contains('due_at')));
        expect(s.sql, isNot(contains('priority')));
      }
    });
  });

  group('getTask and watchTask', () {
    test('a row, null when missing, enriched', () async {
      final db = legacyDb([legacyRow('a', {'client_ref': 'C1'})]);
      final repo = legacyRepo(db, enricher: (sql, tasks) async => [for (final t in tasks) t.copyWith(ownerName: 'Owner ${t.id}')]);
      final t = await repo.getTask('a');
      expect((t!.id, t.ownerName, t.extras['client_ref']), ('a', 'Owner a', 'C1'));
      expect(await repo.getTask('missing'), isNull);
      expect(db.where('WHERE id = ?'), hasLength(2));
    });

    test('watchTask emits the task, null when it is gone, and re-emits on an extraWatchTables change', () async {
      final db = legacyDb([legacyRow('a')], more: {'cases': [{'id': 'k1', 'name': 'One'}]});
      final repo = legacyRepo(
        db,
        extraWatchTables: ['cases'],
        enricher: (sql, tasks) async {
          final name = (await sql.getAll('SELECT * FROM cases')).first['name'] as String;
          return [for (final t in tasks) t.copyWith(ownerName: name)];
        },
      );
      final seen = <String?>[];
      final sub = repo.watchTask('a').listen((t) => seen.add(t?.ownerName));
      await tick();
      await tick();
      expect(db.changeSubscriptions.last, containsAll(['tasks', 'ps_data__tasks', 'cases', 'ps_data__cases']));
      db.tables['cases']!.single['name'] = 'Two';
      db.changes.add(null);
      await tick();
      await tick();
      expect(seen, ['One', 'Two']);
      db.tables['tasks']!.clear();
      db.changes.add(null);
      await tick();
      await tick();
      expect(seen.last, isNull);
      expect(seen, hasLength(3));
      await sub.cancel();
      final missing = await legacyRepo(db).watchTask('zzz').first;
      expect(missing, isNull);
    });
  });

  group('listWhere and watchWhere', () {
    final rows = [
      legacyRow('a', {'client_ref': 'C1', 'case_ref': 'K1', 'due_date': '2026-03-12', 'created_at': '2026-03-01T00:00:00.000Z'}),
      legacyRow('b', {'client_ref': 'C1', 'case_ref': null, 'due_date': '2026-03-13', 'owner_user_id': 'someone-else'}),
      legacyRow('c', {'client_ref': 'C1', 'case_ref': 'K1', 'status': 'done', 'completed_at': '2026-03-10T00:00:00.000Z'}),
      legacyRow('d', {'client_ref': 'C2', 'case_ref': 'K1', 'status': 'cancelled'}),
      legacyRow('e', {'client_ref': 'C1', 'sync_to_calendar': 0}),
    ];

    test('exact SQL and parameters, count independent of limit and offset, a page of the ordered rows', () async {
      final db = legacyDb(rows);
      final repo = legacyRepo(db);
      final page = await repo.listWhere({'client_ref': 'C1'}, limit: 2, offset: 1);
      expect(page.items.map((t) => t.id), ['b', 'c']);
      expect((page.total, page.limit, page.offset), (4, 2, 1));
      expect(db.statements.map((s) => s.toString()), [
        'tx SELECT * FROM tasks WHERE client_ref = ? $dateOrder LIMIT ? OFFSET ? [C1, 2, 1]',
        'tx SELECT COUNT(*) AS n FROM tasks WHERE client_ref = ? [C1]',
      ]);
      final def = await repo.listWhere({'client_ref': 'C1'});
      expect((def.limit, def.offset, def.total, def.items.length), (25, 0, 4, 4));
    });

    test('NOT filtered by owner: another user\'s row is in the page', () async {
      final page = await legacyRepo(legacyDb(rows)).listWhere({'case_ref': null});
      expect(page.items.map((t) => t.id), contains('b'));
      expect(page.items.every((t) => t.ownerUserId == 'user-1'), isFalse);
    });

    test('status filter, a null value, a module name mapped through the shape, several keys', () async {
      final db = legacyDb(rows);
      final repo = legacyRepo(db);
      expect((await repo.listWhere({'client_ref': 'C1'}, status: 'open')).items.map((t) => t.id), ['a', 'b', 'e']);
      expect((await repo.listWhere({'client_ref': 'C1'}, status: 'done')).items.map((t) => t.id), ['c']);
      expect((await repo.listWhere({'case_ref': 'K1'}, status: 'cancelled')).items.map((t) => t.id), ['d']);
      expect((await repo.listWhere({'client_ref': 'C1'}, status: 'all')).total, 4);
      expect((await repo.listWhere({'client_ref': 'C1'}, status: 'bogus')).total, 4);
      expect((await repo.listWhere({'case_ref': null, 'client_ref': 'C1'})).items.map((t) => t.id), ['b', 'e']);
      db.statements.clear();
      final m = await repo.listWhere({'mirror_enabled': false, 'client_ref': 'C1'}, status: 'open');
      expect(m.items.map((t) => t.id), ['e']);
      expect(db.statements.first.toString(), 'tx SELECT * FROM tasks WHERE sync_to_calendar = ? AND client_ref = ? AND status = ? $dateOrder LIMIT ? OFFSET ? [0, C1, open, 25, 0]');
      expect(db.statements.last.toString(), 'tx SELECT COUNT(*) AS n FROM tasks WHERE sync_to_calendar = ? AND client_ref = ? AND status = ? [0, C1, open]');
    });

    test('an unknown key, an absent column and id throw before any SQL', () async {
      final db = legacyDb(rows);
      final repo = legacyRepo(db);
      for (final eq in [
        {'nope': 1},
        {'priority': 3},
        {'id': 'a'},
        {'client_ref; DROP TABLE tasks': 1},
      ]) {
        await expectLater(repo.listWhere(eq), throwsArgumentError);
        expect(() => repo.watchWhere(eq), throwsArgumentError);
      }
      expect(db.statements, isEmpty);
    });

    test('the enricher runs on the page only', () async {
      final seenCounts = <int>[];
      final repo = legacyRepo(legacyDb(rows), enricher: (sql, tasks) async {
        seenCounts.add(tasks.length);
        return [for (final t in tasks) t.copyWith(assigneeName: 'x')];
      });
      final page = await repo.listWhere({'client_ref': 'C1'}, limit: 2);
      expect(page.items.map((t) => t.assigneeName), ['x', 'x']);
      expect(page.total, 4);
      expect(seenCounts, [2]);
    });

    test('watchWhere emits a page and re-emits on a change', () async {
      final db = legacyDb(rows);
      final repo = legacyRepo(db);
      final seen = <List<String>>[];
      final sub = repo.watchWhere({'client_ref': 'C2'}).listen((p) => seen.add([for (final t in p.items) t.id]));
      await tick();
      await tick();
      db.tables['tasks']!.add(legacyRow('f', {'client_ref': 'C2'}));
      db.changes.add(null);
      await tick();
      await tick();
      await sub.cancel();
      expect(seen, [['d'], ['d', 'f']]);
    });
  });

  test('watchList is list(f) as a live snapshot', () async {
    final db = legacyDb([legacyRow('a'), legacyRow('b', {'status': 'done'})]);
    final repo = legacyRepo(db);
    const f = TaskFilters(status: 'open');
    final seen = <List<String>>[];
    final sub = repo.watchList(f).listen((p) => seen.add([for (final t in p.items) t.id]));
    await tick();
    await tick();
    expect(db.changeSubscriptions.last, containsAll(['tasks', 'ps_data__tasks']));
    db.tables['tasks']!.add(legacyRow('c'));
    db.changes.add(null);
    await tick();
    await tick();
    await sub.cancel();
    expect(seen, [['a'], ['a', 'c']]);
    expect((await repo.list(f)).items.map((t) => t.id), ['a', 'c']);
  });
}

/// A fake whose table holds both the legacy and the module columns, so one row set serves both orders.
class FakeSyncDbX {
  FakeSyncDbX(List<SyncRow> rows, Set<String> columns)
      : db = FakeSyncDb.tables({
          'tasks': [
            for (final r in rows) {for (final c in columns) c: r[c]},
          ],
        }, applySql: true, columns: {'tasks': columns});
  final FakeSyncDb db;
}
