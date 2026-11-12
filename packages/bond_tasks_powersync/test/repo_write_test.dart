import 'package:bond_sync_powersync/testing.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

final now = DateTime.utc(2026, 3, 11, 20);
const iso = '2026-03-11T20:00:00.000Z';

List<Stmt> writes(FakeSyncDb db) => [
      for (final s in db.statements)
        if (RegExp(r'^(INSERT|UPDATE|DELETE)').hasMatch(s.sql)) s,
    ];

void main() {
  test('create inserts every column with a client id and returns the stored task', () async {
    final db = fakeTasks([]);
    final repo = repoFor(db, now: now);
    final t = await repo.create(const TaskDraft(
      title: '  Call Dana ',
      id: 'my-id_1',
      notes: 'bring plans',
      dueDate: '2026-03-12',
      priority: TaskPriority.high,
      remindMinutesBefore: -3,
      mirrorEnabled: false,
      links: [TaskLink(kind: 'contact', id: 'c1', label: 'Dana')],
      checklist: [ChecklistItem(id: 'k1', text: 'one')],
    ));
    final w = writes(db).single;
    expect(w.inTx, isTrue);
    expect(
      w.sql,
      'INSERT INTO tasks (id, owner_user_id, created_by, assigned_user_id, title, notes, due_date, due_time, priority, '
      'due_at, status, completed_at, checklist, remind_minutes_before, mirror_enabled, mirror_status, links, source, '
      'created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
    );
    expect(w.params, [
      'my-id_1', 'user-1', 'user-1', null, 'Call Dana', 'bring plans', '2026-03-12', null, 3, //
      null, 'open', null, '[{"id":"k1","text":"one","done_at":null}]', -3, 0, 'pending',
      '[{"kind":"contact","id":"c1","label":"Dana"}]', 'manual', iso, iso,
    ]);
    expect(t.id, 'my-id_1');
    expect(t.title, 'Call Dana');
    expect(t.priority, TaskPriority.high);
    expect(t.mirrorEnabled, isFalse);
    expect(t.ownerUserId, 'user-1');
    expect(t.dueAt, isNull); // date-only: the server fills it
    expect(db.transactions, 1);
  });

  test('every task client id matches the sync id rule', () async {
    final rule = RegExp(r'^[A-Za-z0-9_-]{1,64}$'); // the dispatcher's id rule
    final db = fakeTasks([]);
    final repo = repoFor(db, now: now);
    for (var i = 0; i < 20; i++) {
      expect((await repo.create(TaskDraft(title: 't$i'))).id, matches(rule));
    }
    await repo.create(TaskDraft(title: 'long', id: 'x' * 64));
    await expectLater(repo.create(TaskDraft(title: 'too long', id: 'x' * 65)), throwsArgumentError);
    await expectLater(repo.create(const TaskDraft(title: 'colon', id: 'user:1')), throwsArgumentError);
  });

  test('a generated id is a valid client id and differs each time', () async {
    final db = fakeTasks([]);
    final repo = repoFor(db, now: now);
    final a = await repo.create(const TaskDraft(title: 'a'));
    final b = await repo.create(const TaskDraft(title: 'b'));
    expect(a.id, matches(RegExp(r'^[A-Za-z0-9_-]{1,64}$')));
    expect(a.id, matches(RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')));
    expect(a.id, isNot(b.id));
  });

  test('a timed task stores the device due instant', () async {
    final db = fakeTasks([]);
    final t = await repoFor(db, now: now).create(const TaskDraft(title: 't', id: 'timed', dueDate: '2026-03-13', dueTime: '14:00'));
    final expected = deviceDueAt('2026-03-13', '14:00')!;
    expect(writes(db).single.params[9], isoOf(expected));
    expect(t.dueAt, expected);
  });

  test('an invalid draft or id writes nothing', () async {
    final db = fakeTasks([]);
    final repo = repoFor(db, now: now);
    await expectLater(repo.create(const TaskDraft(title: '  ')), throwsArgumentError);
    await expectLater(repo.create(const TaskDraft(title: 'x', id: 'bad id!')), throwsArgumentError);
    expect(writes(db), isEmpty);
  });

  group('update', () {
    FakeSyncDb dbWith() => fakeTasks([rowOf(fixture('task_timed.json'))]);

    test('writes only the patched columns plus updated_at', () async {
      final db = dbWith();
      final t = await repoFor(db, now: now).update('task-0003', const TaskPatch(title: 'New', notes: Present('n')));
      final w = writes(db).single;
      expect(w.sql, 'UPDATE tasks SET title = ?, notes = ?, updated_at = ? WHERE id = ?');
      expect(w.params, ['New', 'n', iso, 'task-0003']);
      expect(t.title, 'New');
      expect(t.notes, 'n');
      expect(t.dueAt, DateTime.utc(2026, 3, 13, 21)); // untouched
    });

    test('Present(null) clears a column; an empty patch writes nothing', () async {
      final db = dbWith();
      final repo = repoFor(db, now: now);
      await repo.update('task-0003', const TaskPatch(priority: Present(null)));
      expect(writes(db).single.sql, 'UPDATE tasks SET priority = ?, updated_at = ? WHERE id = ?');
      expect(writes(db).single.params, [null, iso, 'task-0003']);
      await repo.update('task-0003', const TaskPatch());
      expect(writes(db), hasLength(1));
    });

    test('changing the time recomputes due_at; resending the same values does not', () async {
      final db = dbWith();
      final repo = repoFor(db, now: now);
      await repo.update('task-0003', const TaskPatch(dueDate: Present('2026-03-13'), dueTime: Present('14:00')));
      expect(writes(db).single.sql, 'UPDATE tasks SET due_date = ?, due_time = ?, updated_at = ? WHERE id = ?');
      db.statements.clear();
      await repo.update('task-0003', const TaskPatch(dueTime: Present('16:30')));
      final w = writes(db).single;
      expect(w.sql, 'UPDATE tasks SET due_time = ?, due_at = ?, updated_at = ? WHERE id = ?');
      expect(w.params[0], '16:30');
      expect(w.params[1], isoOf(deviceDueAt('2026-03-13', '16:30')!));
    });

    test('clearing the date clears due_at', () async {
      final db = dbWith();
      final t = await repoFor(db, now: now).update('task-0003', const TaskPatch(dueDate: Present(null), dueTime: Present(null)));
      expect(writes(db).single.sql, 'UPDATE tasks SET due_date = ?, due_time = ?, due_at = ?, updated_at = ? WHERE id = ?');
      expect(t.dueDate, isNull);
      expect(t.dueAt, isNull);
    });

    test('a date-only result never gets a device instant, even when the patch carries one', () async {
      final dated = {...rowOf(fixture('task_timed.json')), 'due_time': null, 'due_at': '2026-03-14T00:00:00Z', 'due_date': '2026-03-13'};
      final db = fakeTasks([dated]);
      final t = await repoFor(db, now: now).update(
        'task-0003',
        TaskPatch(dueDate: const Present('2026-03-20'), dueAt: Present(DateTime.utc(2026, 3, 20, 21))),
      );
      final w = writes(db).single;
      expect(w.sql, 'UPDATE tasks SET due_date = ?, due_at = ?, updated_at = ? WHERE id = ?');
      expect(w.params, ['2026-03-20', null, iso, 'task-0003']);
      expect(t.dueAt, isNull);
    });

    test('a timed result takes the patch instant; removing the time makes it date-only (due_at null)', () async {
      final db = dbWith();
      final repo = repoFor(db, now: now);
      await repo.update('task-0003', TaskPatch(dueAt: Present(DateTime.utc(2026, 3, 13, 22))));
      expect(writes(db).single.params, ['2026-03-13T22:00:00.000Z', iso, 'task-0003']);
      db.statements.clear();
      await repo.update('task-0003', const TaskPatch(dueTime: Present(null)));
      expect(writes(db).single.sql, 'UPDATE tasks SET due_time = ?, due_at = ?, updated_at = ? WHERE id = ?');
      expect(writes(db).single.params, [null, null, iso, 'task-0003']);
    });

    test('clearing only the date also clears the time and the due instant', () async {
      final db = dbWith();
      final t = await repoFor(db, now: now).update('task-0003', const TaskPatch(dueDate: Present(null)));
      final w = writes(db).single;
      expect(w.sql, 'UPDATE tasks SET due_date = ?, due_time = ?, due_at = ?, updated_at = ? WHERE id = ?');
      expect(w.params, [null, null, null, iso, 'task-0003']);
      expect(t.dueTime, isNull);
      expect(t.dueAt, isNull);
    });

    test('checklist and links go in as JSON text; a missing task throws', () async {
      final db = dbWith();
      final repo = repoFor(db, now: now);
      final t = await repo.update('task-0003', const TaskPatch(checklist: [ChecklistItem(id: 'a', text: 'x')], links: []));
      expect(writes(db).single.params.take(2), ['[{"id":"a","text":"x","done_at":null}]', '[]']);
      expect(t.checklist.single.text, 'x');
      await expectLater(repo.update('nope', const TaskPatch(title: 'x')), throwsStateError);
    });
  });

  group('status', () {
    FakeSyncDb dbWith([String status = 'open']) =>
        fakeTasks([{...rowOf(fixture('task_timed.json')), 'status': status}]);
    const sql = 'UPDATE tasks SET status = ?, completed_at = ?, updated_at = ?, _metadata = ? WHERE id = ?';

    test('complete', () async {
      final db = dbWith();
      final t = await repoFor(db, now: now).complete('task-0003');
      expect(writes(db).single.sql, sql);
      expect(writes(db).single.params, ['done', iso, iso, '{"action":"complete"}', 'task-0003']);
      expect(t.status, TaskStatus.done);
      expect(t.completedAt, now);
    });

    test('reopen clears completed_at', () async {
      final db = fakeTasks([{...rowOf(fixture('task_timed.json')), 'status': 'done', 'completed_at': iso}]);
      final t = await repoFor(db, now: now).reopen('task-0003');
      expect(writes(db).single.params, ['open', null, iso, '{"action":"reopen"}', 'task-0003']);
      expect(t.status, TaskStatus.open);
      expect(t.completedAt, isNull);
    });

    test('cancel', () async {
      final db = dbWith();
      final t = await repoFor(db, now: now).cancel('task-0003');
      expect(writes(db).single.params, ['cancelled', null, iso, '{"action":"cancel"}', 'task-0003']);
      expect(t.status, TaskStatus.cancelled);
    });

    test('asking for the status the task already has writes nothing', () async {
      final done = {...rowOf(fixture('task_timed.json')), 'status': 'done', 'completed_at': '2026-03-10T09:00:00Z'};
      final db = fakeTasks([done]);
      final repo = repoFor(db, now: now);
      final t = await repo.complete('task-0003');
      expect(writes(db), isEmpty);
      expect(t.completedAt, DateTime.utc(2026, 3, 10, 9)); // not rewritten
      final open = dbWith();
      await repoFor(open, now: now).reopen('task-0003');
      expect(writes(open), isEmpty);
      final cancelled = dbWith('cancelled');
      await repoFor(cancelled, now: now).cancel('task-0003');
      expect(writes(cancelled), isEmpty);
    });

    test('an unknown id throws and writes nothing', () async {
      final db = dbWith();
      await expectLater(repoFor(db, now: now).complete('nope'), throwsStateError);
      expect(writes(db), isEmpty);
    });
  });

  test('delete removes the row by id; refresh does nothing', () async {
    final db = fakeTasks([rowOf(fixture('task_timed.json')), {...rowOf(fixture('task.json'))}]);
    final repo = repoFor(db, now: now);
    await repo.delete('task-0003');
    expect(writes(db).single.sql, 'DELETE FROM tasks WHERE id = ?');
    expect(writes(db).single.params, ['task-0003']);
    expect(db.tables['tasks']!.map((r) => r['id']), isNot(contains('task-0003')));
    await repo.refresh();
    expect(writes(db), hasLength(1));
  });

  test('the fake rejects a wrong column name, so a typo in the adapter cannot pass', () async {
    final db = fakeTasks([rowOf(fixture('task_timed.json'))]);
    await expectLater(db.execute('UPDATE tasks SET titel = ? WHERE id = ?', ['x', 'task-0003']), throwsStateError);
  });
}

String isoOf(DateTime t) => DateTime.fromMillisecondsSinceEpoch(t.millisecondsSinceEpoch, isUtc: true).toIso8601String();
