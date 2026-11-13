import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_sync_powersync/testing.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';

import 'shape_support.dart';

final String now = '2026-03-11T20:00:00.000Z';

List<Stmt> writes(FakeSyncDb db) => [
      for (final s in db.statements)
        if (RegExp(r'^(INSERT|UPDATE|DELETE)').hasMatch(s.sql)) s,
    ];

String metaOf(String a) => '{"action":"$a"}';

void main() {
  group('SQL at the legacy shape', () {
    test('INSERT names only declared columns, writes the flag to sync_to_calendar, drops absent values', () async {
      final db = legacyDb([]);
      final repo = legacyRepo(db);
      final t = await repo.create(const TaskDraft(
        title: ' Hello ',
        id: 't1',
        notes: 'n',
        dueDate: '2026-03-13',
        dueTime: '14:00',
        priority: TaskPriority.high,
        mirrorEnabled: false,
        checklist: [ChecklistItem(id: 'c1', text: 'x')],
        remindMinutesBefore: 30,
        extras: {'client_ref': 'C1', 'not_declared': 'x'},
      ));
      final w = writes(db).single;
      expect(
        w.sql,
        'INSERT INTO tasks (id, owner_user_id, created_by, assigned_user_id, title, notes, due_date, due_time, status, completed_at, '
        'sync_to_calendar, mirror_status, source, created_at, updated_at, client_ref) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
      );
      expect(w.params, ['t1', 'user-1', 'user-1', null, 'Hello', 'n', '2026-03-13', '14:00', 'open', null, 0, 'pending', 'manual', now, now, 'C1']);
      expect((t.mirrorEnabled, t.priority, t.extras['client_ref']), (false, null, 'C1'));
      expect(t.checklist, isEmpty);
      expect(t.dueAt, deviceDueAt('2026-03-13', '14:00')); // derived on read: the legacy table holds no due_at
    });

    test('UPDATE names only declared columns; absent values are dropped; the flag goes to sync_to_calendar', () async {
      final db = legacyDb([legacyRow('a', {'client_ref': 'C0'})]);
      final repo = legacyRepo(db);
      await repo.update(
        'a',
        const TaskPatch(title: 'N', mirrorEnabled: false, priority: Present(TaskPriority.high), remindMinutesBefore: 5, extras: {'client_ref': 'C9'}),
      );
      final w = writes(db).single;
      expect(w.sql, 'UPDATE tasks SET title = ?, sync_to_calendar = ?, client_ref = ?, updated_at = ? WHERE id = ?');
      expect(w.params, ['N', 0, 'C9', now, 'a']);
      db.statements.clear();
      await repo.update('a', const TaskPatch(dueDate: Present('2026-03-20'))); // due_at would follow the date: dropped
      expect(writes(db).single.sql, 'UPDATE tasks SET due_date = ?, updated_at = ? WHERE id = ?');
      db.statements.clear();
      await repo.update('a', const TaskPatch(priority: Present(TaskPriority.low))); // only absent values: nothing to write
      expect(writes(db), isEmpty);
    });

    test('status SQL: today\'s text by default, completed_by only with writeCompletedBy', () async {
      final db = legacyDb([legacyRow('a'), legacyRow('b')]);
      final repo = legacyRepo(db);
      await repo.complete('a');
      expect(writes(db).single.sql, 'UPDATE tasks SET status = ?, completed_at = ?, updated_at = ?, _metadata = ? WHERE id = ?');
      expect(writes(db).single.params, ['done', now, now, metaOf('complete'), 'a']);
      expect(db.tables['tasks']!.first.containsKey('completed_by'), isTrue);
      expect(db.tables['tasks']!.first['completed_by'], isNull);
    });

    test('writeCompletedBy: complete writes the user, reopen and cancel write NULL', () async {
      final db = legacyDb([legacyRow('a'), legacyRow('b')]);
      final repo = legacyRepo(db, writeCompletedBy: true);
      const sql = 'UPDATE tasks SET status = ?, completed_at = ?, completed_by = ?, updated_at = ?, _metadata = ? WHERE id = ?';
      await repo.complete('a');
      expect(writes(db).last.sql, sql);
      expect(writes(db).last.params, ['done', now, 'user-1', now, metaOf('complete'), 'a']);
      expect(db.tables['tasks']!.first['completed_by'], 'user-1');
      await repo.reopen('a');
      expect(writes(db).last.params, ['open', null, null, now, metaOf('reopen'), 'a']);
      expect(db.tables['tasks']!.first['completed_by'], isNull);
      await repo.complete('b');
      await repo.cancel('b');
      expect(writes(db).last.sql, sql);
      expect(writes(db).last.params, ['cancelled', null, null, now, metaOf('cancel'), 'b']);
    });

    test('writeCompletedBy is skipped when completed_by is absent', () async {
      final shape = TaskTableShape(absent: {...legacyShape.absent, 'completed_by'}, rename: legacyShape.rename);
      final cols = legacyColumns()..remove('completed_by');
      final db = FakeSyncDb.tables({'tasks': [{for (final c in cols) c: null, 'id': 'a', 'owner_user_id': 'user-1', 'status': 'open'}]}, applySql: true, columns: {'tasks': cols});
      await legacyRepo(db, shape: shape, writeCompletedBy: true).complete('a');
      expect(writes(db).single.sql, 'UPDATE tasks SET status = ?, completed_at = ?, updated_at = ?, _metadata = ? WHERE id = ?');
    });

    test('the default repository writes exactly today\'s statements for a status change', () async {
      final db = FakeSyncDb.tables({'tasks': [{'id': 'a', 'owner_user_id': 'user-1', 'status': 'open'}]}, applySql: true);
      await PowerSyncTaskRepository(db, userId: 'user-1', clock: TaskClock(() => t0), writeCompletedBy: false).complete('a');
      expect(writes(db).single.sql, 'UPDATE tasks SET status = ?, completed_at = ?, updated_at = ?, _metadata = ? WHERE id = ?');
    });
  });

  group('mirrorStatusOnWrite', () {
    test('called on create, update, complete, reopen and cancel with after and before; a value is written', () async {
      final calls = <(Map<String, Object?>, Map<String, Object?>?)>[];
      final db = legacyDb([legacyRow('a', {'client_ref': 'C0'}), legacyRow('b', {'status': 'done', 'completed_at': now})]);
      final repo = legacyRepo(db, mirrorStatusOnWrite: (after, before) {
        calls.add((Map.of(after), before == null ? null : Map.of(before)));
        return 'skipped';
      });
      await repo.create(const TaskDraft(title: 'New', id: 'n'));
      expect(calls.single.$2, isNull);
      expect((calls.single.$1['id'], calls.single.$1['title'], calls.single.$1['mirror_status']), ('n', 'New', 'pending'));
      expect(writes(db).single.params[11], 'skipped'); // the mirror_status slot of the INSERT
      expect(db.tables['tasks']!.last['mirror_status'], 'skipped');

      calls.clear();
      db.statements.clear();
      await repo.update('a', const TaskPatch(title: 'T2'));
      expect(writes(db).single.sql, 'UPDATE tasks SET title = ?, updated_at = ?, mirror_status = ? WHERE id = ?');
      expect(calls.single.$2!['title'], 'T a');
      expect((calls.single.$1['title'], calls.single.$1['client_ref'], calls.single.$1['status'], calls.single.$1['updated_at']), ('T2', 'C0', 'open', now));

      calls.clear();
      await repo.complete('a');
      expect((calls.single.$1['status'], calls.single.$1['completed_at'], calls.single.$2!['status']), ('done', now, 'open'));
      calls.clear();
      db.statements.clear();
      await repo.reopen('a');
      expect((calls.single.$1['status'], calls.single.$1['completed_at'], calls.single.$2!['status']), ('open', null, 'done'));
      expect(writes(db).single.sql, 'UPDATE tasks SET status = ?, completed_at = ?, updated_at = ?, mirror_status = ?, _metadata = ? WHERE id = ?');
      calls.clear();
      await repo.cancel('a');
      expect((calls.single.$1['status'], calls.single.$2!['status']), ('cancelled', 'open'));
      expect(db.tables['tasks']!.first['mirror_status'], 'skipped');
    });

    test('null keeps today\'s values: create writes pending, the others leave mirror_status alone', () async {
      final db = legacyDb([legacyRow('a', {'mirror_status': 'mirrored'})]);
      final repo = legacyRepo(db, mirrorStatusOnWrite: (a, b) => null);
      await repo.create(const TaskDraft(title: 'N', id: 'n'));
      expect(db.tables['tasks']!.last['mirror_status'], 'pending');
      db.statements.clear();
      await repo.update('a', const TaskPatch(title: 'x'));
      await repo.complete('a');
      for (final w in writes(db)) {
        expect(w.sql, isNot(contains('mirror_status')));
      }
      expect(db.tables['tasks']!.first['mirror_status'], 'mirrored');
    });

    test('not called for an update that writes nothing or an action already satisfied', () async {
      var n = 0;
      final db = legacyDb([legacyRow('a'), legacyRow('b', {'status': 'done'})]);
      final repo = legacyRepo(db, mirrorStatusOnWrite: (a, b) {
        n++;
        return null;
      });
      await repo.update('a', const TaskPatch());
      await repo.complete('b');
      await repo.reopen('a');
      expect(n, 0);
    });

    test('a throw fails the write and nothing is written', () async {
      final db = legacyDb([legacyRow('a')]);
      final repo = legacyRepo(db, mirrorStatusOnWrite: (a, b) => throw StateError('rule'));
      await expectLater(repo.create(const TaskDraft(title: 'N', id: 'n')), throwsStateError);
      await expectLater(repo.update('a', const TaskPatch(title: 'x')), throwsStateError);
      await expectLater(repo.complete('a'), throwsStateError);
      expect(writes(db), isEmpty);
      expect(db.tables['tasks'], hasLength(1));
      expect(db.tables['tasks']!.single['status'], 'open');
    });

    test('ignored when mirror_status is absent', () async {
      final shape = TaskTableShape(absent: {...legacyShape.absent, 'mirror_status'}, rename: legacyShape.rename);
      final cols = legacyColumns()..remove('mirror_status');
      final db = FakeSyncDb.tables({'tasks': <SyncRow>[]}, applySql: true, columns: {'tasks': cols});
      await legacyRepo(db, shape: shape, mirrorStatusOnWrite: (a, b) => 'failed').create(const TaskDraft(title: 'N', id: 'n'));
      expect(writes(db).single.sql, isNot(contains('mirror_status')));
    });
  });

  group('prepare', () {
    test('changes a value, adds an extra column, reads another table through tx', () async {
      final db = legacyDb([], more: {'cases': [{'id': 'k1', 'name': 'Case One'}]}, moreColumns: {'cases': {'id', 'name'}});
      final kinds = <TaskWriteKind>[];
      final repo = legacyRepo(db, prepare: (tx, w) async {
        kinds.add(w.kind);
        final c = await tx.getOptional('SELECT * FROM cases WHERE id = ?', ['k1']);
        return {...w.values, 'title': 'Prepared', 'case_ref': c!['name'], 'case_file_no': 'F-1'};
      });
      final t = await repo.create(const TaskDraft(title: 'Raw', id: 'n', extras: {'client_ref': 'C1'}));
      expect(t.title, 'Prepared');
      expect((t.extras['case_ref'], t.extras['case_file_no'], t.extras['client_ref']), ('Case One', 'F-1', 'C1'));
      final w = writes(db).single;
      expect(w.sql, contains('case_ref'));
      expect(w.sql, contains('case_file_no'));
      expect(kinds, [TaskWriteKind.create]);
    });

    test('the write it gets: create has every value, update has the patch columns and the stored row', () async {
      final seen = <TaskWrite>[];
      final db = legacyDb([legacyRow('a')]);
      final repo = legacyRepo(db, prepare: (tx, w) async {
        seen.add(w);
        return w.values;
      });
      await repo.create(const TaskDraft(title: 'N', id: 'n', mirrorEnabled: false));
      expect(seen.single.before, isNull);
      expect((seen.single.values['sync_to_calendar'], seen.single.values['updated_at'], seen.single.values.containsKey('id')), (0, now, false));
      expect(seen.single.values.containsKey('priority'), isFalse);
      seen.clear();
      await repo.update('a', const TaskPatch(title: 'T2', mirrorEnabled: false));
      expect(seen.single.kind, TaskWriteKind.update);
      expect(seen.single.values, {'title': 'T2', 'sync_to_calendar': 0});
      expect(seen.single.before!['id'], 'a');
      await repo.complete('a');
      await repo.delete('a');
      expect(seen, hasLength(1), reason: 'prepare is for create and update only');
    });

    test('an illegal key throws ArgumentError and nothing is written', () async {
      for (final bad in [
        {'priority': 3}, // absent
        {'nope': 1}, // unknown
        {'id': 'x'},
        {'mirror_enabled': 1}, // the module name of a renamed column is not a local column
        {'_metadata': 'x'},
      ]) {
        final db = legacyDb([legacyRow('a')]);
        final repo = legacyRepo(db, prepare: (tx, w) async => {...w.values, ...bad});
        await expectLater(repo.create(const TaskDraft(title: 'N', id: 'n')), throwsArgumentError, reason: '$bad');
        await expectLater(repo.update('a', const TaskPatch(title: 'x')), throwsArgumentError, reason: '$bad');
        expect(writes(db), isEmpty, reason: '$bad');
      }
    });

    test('update with an empty patch: prepare may add a column; an empty result writes nothing', () async {
      final db = legacyDb([legacyRow('a')]);
      var after = 0;
      var add = true;
      final repo = legacyRepo(
        db,
        prepare: (tx, w) async => add ? {'case_file_no': 'F-2'} : {},
        afterWrite: (tx, w) async => after++,
      );
      final t = await repo.update('a', const TaskPatch());
      expect(writes(db).single.sql, 'UPDATE tasks SET case_file_no = ?, updated_at = ? WHERE id = ?');
      expect(writes(db).single.params, ['F-2', now, 'a']);
      expect(t.extras['case_file_no'], 'F-2');
      expect(after, 1);
      db.statements.clear();
      add = false;
      await repo.update('a', const TaskPatch(title: 'dropped by prepare'));
      expect(writes(db), isEmpty);
      expect(after, 1, reason: 'nothing written: no afterWrite');
    });
  });

  group('afterWrite', () {
    test('runs after every kind with kind, id, before and values', () async {
      final seen = <TaskWrite>[];
      final db = legacyDb([legacyRow('a'), legacyRow('b')]);
      final repo = legacyRepo(db, afterWrite: (tx, w) async => seen.add(w));
      await repo.create(const TaskDraft(title: 'N', id: 'n', mirrorEnabled: false));
      await repo.update('a', const TaskPatch(title: 'T2'));
      await repo.complete('a');
      await repo.reopen('a');
      await repo.cancel('a');
      await repo.delete('b');
      expect(seen.map((w) => (w.kind, w.id)), [
        (TaskWriteKind.create, 'n'),
        (TaskWriteKind.update, 'a'),
        (TaskWriteKind.complete, 'a'),
        (TaskWriteKind.reopen, 'a'),
        (TaskWriteKind.cancel, 'a'),
        (TaskWriteKind.delete, 'b'),
      ]);
      expect(seen[0].before, isNull);
      expect((seen[0].values['title'], seen[0].values['sync_to_calendar'], seen[0].values.containsKey('id')), ('N', 0, false));
      expect(seen[1].before!['title'], 'T a');
      expect(seen[1].values, {'title': 'T2', 'updated_at': now});
      expect(seen[2].before!['status'], 'open');
      expect(seen[2].values, {'status': 'done', 'completed_at': now, 'updated_at': now});
      expect(seen[3].before!['status'], 'done');
      expect(seen[3].values, {'status': 'open', 'completed_at': null, 'updated_at': now});
      expect(seen[4].before!['status'], 'open');
      expect(seen[4].values['status'], 'cancelled');
      expect(seen[5].before!['id'], 'b');
      expect(seen[5].values, isEmpty);
    });

    test('values carry completed_by under writeCompletedBy; delete of a missing row has a null before', () async {
      final seen = <TaskWrite>[];
      final repo = legacyRepo(legacyDb([legacyRow('a')]), writeCompletedBy: true, afterWrite: (tx, w) async => seen.add(w));
      await repo.complete('a');
      expect(seen.single.values['completed_by'], 'user-1');
      seen.clear();
      await repo.delete('missing');
      expect((seen.single.kind, seen.single.before), (TaskWriteKind.delete, null));
    });

    test('not called for a satisfied status action or an empty update; delete reads before only when hooked', () async {
      var n = 0;
      final db = legacyDb([legacyRow('a'), legacyRow('b', {'status': 'done'})]);
      final repo = legacyRepo(db, afterWrite: (tx, w) async => n++);
      await repo.complete('b');
      await repo.reopen('a');
      await repo.update('a', const TaskPatch());
      await repo.update('a', const TaskPatch(priority: Present(TaskPriority.low)));
      expect(n, 0);
      expect(writes(db), isEmpty);
      final plain = legacyDb([legacyRow('a')]);
      await legacyRepo(plain).delete('a');
      expect(plain.statements.map((s) => s.sql), ['DELETE FROM tasks WHERE id = ?']);
    });

    test('a throw from afterWrite fails the write', () async {
      final repo = legacyRepo(legacyDb([legacyRow('a')]), afterWrite: (tx, w) async => throw StateError('after'));
      await expectLater(repo.complete('a'), throwsStateError);
    });
  });

  test('hook order: prepare, mirror, statement, afterWrite', () async {
    final db = legacyDb([]);
    final log = <String>[];
    int sqlCount() => writes(db).length;
    final repo = legacyRepo(
      db,
      prepare: (tx, w) async {
        log.add('prepare:${sqlCount()}');
        return w.values;
      },
      mirrorStatusOnWrite: (a, b) {
        log.add('mirror:${sqlCount()}');
        return null;
      },
      afterWrite: (tx, w) async => log.add('after:${sqlCount()}'),
    );
    await repo.create(const TaskDraft(title: 'N', id: 'n'));
    expect(log, ['prepare:0', 'mirror:0', 'after:1']);
    log.clear();
    await repo.update('n', const TaskPatch(title: 'x'));
    expect(log, ['prepare:1', 'mirror:1', 'after:2']);
  });
}
