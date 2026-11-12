import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

final now = DateTime.utc(2026, 3, 11, 20);

List<String> ids(List<Task> l) => [for (final t in l) t.id];

List<Map<String, Object?>> section(Map<String, Object?> json, String k) => [
      for (final t in json[k]! as List) (t as Map).cast<String, Object?>(),
    ];

void main() {
  final today = fixture('today.json');
  final rows = [
    for (final k in ['overdue', 'today', 'undated', 'done_today']) ...section(today, k).map(rowOf),
    rowOf(fixture('task_timed.json')), // open, due on the 13th: in no section
  ];

  group('today and summary on fixtures/tasks/today.json', () {
    test('sections and counts equal the fixture', () async {
      final repo = repoFor(fakeTasks(rows), now: now);
      final got = await repo.today();
      expect(ids(got.overdue), ids(TaskToday.fromJson(today).overdue));
      expect(ids(got.today), ids(TaskToday.fromJson(today).today));
      expect(ids(got.undated), ids(TaskToday.fromJson(today).undated));
      expect(ids(got.doneToday), ids(TaskToday.fromJson(today).doneToday));
      expect(got.counts.toJson(), today['counts']);
    }, skip: inLosAngeles() ? false : kZoneSkip);

    test('summary equals the fixture', () async {
      final repo = repoFor(fakeTasks(rows), now: now);
      final s = await repo.summary();
      final want = fixture('summary.json');
      expect((s.open, s.overdue, s.dueToday, s.noDate), (want['open'], want['overdue'], want['due_today'], want['no_date']));
    }, skip: inLosAngeles() ? false : kZoneSkip);

    test('only the user\'s own tasks count (owner or assignee), others are ignored', () async {
      final other = rowOf(fixture('task_timed.json'))
        ..['id'] = 'x1'
        ..['owner_user_id'] = 'user-9'
        ..['assigned_user_id'] = null;
      final assigned = rowOf(fixture('task_timed.json'))
        ..['id'] = 'x2'
        ..['owner_user_id'] = 'user-9'
        ..['assigned_user_id'] = 'user-1';
      final db = fakeTasks([other, assigned]);
      final repo = repoFor(db, now: now);
      expect((await repo.summary()).open, 1);
      final open = db.statements.where((s) => s.sql.contains("status = 'open'")).single;
      expect(open.params, ['user-1', 'user-1']);
      expect(open.sql, contains('(owner_user_id = ? OR assigned_user_id = ?)'));
    });
  });

  test('a date-only task dated yesterday with a due instant still ahead is listed under today', () async {
    final row = {
      ...rowOf(fixture('task_timed.json')),
      'id': 'y1',
      'due_date': '2026-03-10',
      'due_time': null,
      'due_at': '2026-03-12T00:00:00Z', // the instant is still in the future at 2026-03-11T20:00Z
    };
    final repo = repoFor(fakeTasks([row]), now: now);
    final t = await repo.today();
    expect(ids(t.today), ['y1']);
    expect(t.overdue, isEmpty);
    expect(t.counts.today, 1);
    final s = await repo.summary();
    expect((s.open, s.overdue, s.dueToday), (1, 0, 1));
  }, skip: inLosAngeles() ? false : kZoneSkip);

  test('done today needs completed_at inside the local day', () async {
    final base = rowOf(fixture('task_timed.json'))
      ..['status'] = 'done'
      ..['due_at'] = null
      ..['due_date'] = null
      ..['due_time'] = null;
    final inside = {...base, 'id': 'in', 'completed_at': '2026-03-11T15:20:00Z'};
    final yesterday = {...base, 'id': 'y', 'completed_at': '2026-03-10T15:20:00Z'};
    final tomorrow = {...base, 'id': 't', 'completed_at': '2026-03-12T15:20:00.000Z'};
    final repo = repoFor(fakeTasks([inside, yesterday, tomorrow]), now: now);
    expect(ids((await repo.today()).doneToday), ['in']);
  }, skip: inLosAngeles() ? false : kZoneSkip);

  test('watchOpen asks for open tasks of the user ordered by due, newest created, id', () async {
    final a = {...rowOf(fixture('task_timed.json')), 'id': 'b', 'due_at': '2026-03-13T21:00:00Z'};
    final b = {...a, 'id': 'a', 'due_at': '2026-03-12T21:00:00Z'};
    final c = {...a, 'id': 'c', 'due_at': null, 'due_date': null, 'due_time': null};
    final d = {...a, 'id': 'd', 'status': 'done'};
    final e = {...a, 'id': 'e', 'owner_user_id': 'user-2', 'assigned_user_id': null};
    final f = {...a, 'id': 'a2', 'created_at': '2026-03-05T12:00:00Z'}; // same due as a: newer created first
    final db = fakeTasks([a, b, c, d, e, f]);
    final repo = repoFor(db, now: now);
    final first = await repo.watchOpen().first;
    expect(ids(first), ['a', 'a2', 'b', 'c']);
    final sql = db.statements.last.sql;
    expect(sql, contains('ORDER BY due_at IS NULL, due_at, created_at DESC, id'));
  });

  test('watchOpen emits again when a task changes', () async {
    final db = fakeTasks([rowOf(fixture('task_timed.json'))]);
    final repo = repoFor(db, now: now);
    final seen = <List<String>>[];
    final sub = repo.watchOpen().listen((l) => seen.add(ids(l)));
    await pumpEventQueue();
    await repo.complete('task-0003');
    await pumpEventQueue();
    await sub.cancel();
    expect(seen, [
      ['task-0003'],
      <String>[],
    ]);
  });

  group('list', () {
    final base = rowOf(fixture('task_timed.json'));
    final data = [
      {...base, 'id': 'l1', 'due_date': '2026-03-12', 'due_time': null, 'due_at': '2026-03-13T00:00:00Z'},
      {...base, 'id': 'l2', 'due_date': '2026-03-14', 'due_time': null, 'due_at': '2026-03-15T00:00:00Z'},
      {...base, 'id': 'l3', 'due_date': null, 'due_time': null, 'due_at': null, 'links': '[{"kind":"loan","id":"loan-9","label":null}]'},
      {...base, 'id': 'l4', 'status': 'done', 'due_date': '2026-03-12', 'due_time': null, 'due_at': '2026-03-13T00:00:00Z'},
      {...base, 'id': 'l5', 'owner_user_id': 'user-2', 'assigned_user_id': null, 'due_date': '2026-03-12', 'due_time': null},
    ];

    Future<List<String>> run(TaskFilters f) async => ids((await repoFor(fakeTasks(data), now: now).list(f)).items);

    test('default is my open tasks', () async => expect(await run(const TaskFilters()), ['l1', 'l2', 'l3']));
    test('status done', () async => expect(await run(const TaskFilters(status: 'done')), ['l4']));
    test('status all', () async => expect(await run(const TaskFilters(status: 'all')), ['l1', 'l4', 'l2', 'l3']));
    test('scope all includes other owners', () async => expect(await run(const TaskFilters(scope: 'all')), contains('l5')));
    test('date range by day', () async {
      expect(await run(const TaskFilters(dueFrom: '2026-03-13', dueTo: '2026-03-14')), ['l2']);
      expect(await run(const TaskFilters(onOrBefore: '2026-03-12')), ['l1']);
      expect(await run(const TaskFilters(onOrBefore: '2026-03-12', includeUndated: true)), ['l1', 'l3']);
    });
    test('no date', () async => expect(await run(const TaskFilters(noDate: true)), ['l3']));
    test('link filter decodes the links', () async {
      expect(await run(const TaskFilters(linkId: 'loan-9')), ['l3']);
      expect(await run(const TaskFilters(linkId: 'loan-9', linkKind: 'loan')), ['l3']);
      expect(await run(const TaskFilters(linkId: 'loan-9', linkKind: 'contact')), isEmpty);
    });
    test('paging reports the total', () async {
      final page = await repoFor(fakeTasks(data), now: now).list(const TaskFilters(limit: 1, offset: 1));
      expect(ids(page.items), ['l2']);
      expect(page.total, 3);
    });
  });
}
