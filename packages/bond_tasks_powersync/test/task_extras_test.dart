import 'package:bond_sync_powersync/testing.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:powersync/powersync.dart' show Column, Index, IndexedColumn;

import 'support.dart';

final now = DateTime.utc(2026, 3, 11, 20);

Set<String> _cols() => {'id', ...taskColumnNames(), 'loan_id', 'rank'};

FakeSyncDb _db(List<Map<String, Object?>> rows, {Map<String, List<Map<String, Object?>>> more = const {}}) =>
    FakeSyncDb.tables({'tasks': rows, ...more}, applySql: true, columns: {'tasks': _cols()});

PowerSyncTaskRepository _repo(FakeSyncDb db, {TaskEnricher? enricher, List<String> watch = const []}) =>
    PowerSyncTaskRepository(
      db,
      userId: 'user-1',
      clock: TaskClock(() => now),
      extraColumns: const {'loan_id', 'rank'},
      enricher: enricher,
      extraWatchTables: watch,
    );

void main() {
  test('tasks_tables_extra_columns: adds columns and indexes, refuses a clash', () {
    final t = tasksTables(
      extraColumns: [const Column.text('loan_id'), const Column.integer('rank')],
      extraIndexes: const [Index('loan', [IndexedColumn('loan_id')])],
    ).single;
    expect(t.columns.map((c) => c.name), containsAll(['loan_id', 'rank', ...kTaskColumns]));
    expect(t.columns.length, kTaskColumns.length + 2);
    expect(t.columns.firstWhere((c) => c.name == 'rank').type.sqlite, 'INTEGER');
    expect(t.indexes.map((i) => i.name), contains('loan'));
    expect(tasksTables().single.columns.length, kTaskColumns.length, reason: 'default unchanged');
    for (final bad in ['title', 'id', 'owner_name', 'overdue']) {
      expect(() => tasksTables(extraColumns: [Column.text(bad)]), throwsArgumentError, reason: bad);
    }
    expect(() => tasksTables(extraColumns: [const Column.text('a'), const Column.text('a')]), throwsArgumentError);
  });

  test('insert_writes_extras: only the declared extras are written, in the same insert', () async {
    final db = _db([]);
    final t = await _repo(db).create(const TaskDraft(
      title: 'T',
      id: 'x1',
      extras: {'loan_id': 'L1', 'rank': 2, 'sneaky': 'no', 'title': 'no'},
    ));
    final w = db.statements.firstWhere((s) => s.sql.startsWith('INSERT'));
    expect(w.sql, endsWith('created_at, updated_at, loan_id, rank) VALUES (${List.filled(22, '?').join(', ')})'));
    expect(w.params.sublist(w.params.length - 2), ['L1', 2]);
    expect(w.params, isNot(contains('no')));
    expect(db.statements.where((s) => s.sql.startsWith('INSERT')), hasLength(1));
    expect(t.extras, {'loan_id': 'L1', 'rank': 2});
  });

  test('insert without the extras keeps the old statement', () async {
    final db = _db([]);
    await PowerSyncTaskRepository(db, userId: 'user-1', clock: TaskClock(() => now))
        .create(const TaskDraft(title: 'T', id: 'x1', extras: {'loan_id': 'L1'}));
    final w = db.statements.firstWhere((s) => s.sql.startsWith('INSERT'));
    expect(w.sql, isNot(contains('loan_id')));
  });

  test('patch_extras_only_allowed_columns', () async {
    final row = {...rowOf(fixture('task_timed.json')), 'loan_id': 'L1', 'rank': 1};
    final db = _db([row]);
    final t = await _repo(db).update('task-0003', const TaskPatch(extras: {'loan_id': 'L2', 'sneaky': 'x'}));
    final w = db.statements.firstWhere((s) => s.sql.startsWith('UPDATE'));
    expect(w.sql, 'UPDATE tasks SET loan_id = ?, updated_at = ? WHERE id = ?');
    expect(t.extras, {'loan_id': 'L2', 'rank': 1});
    final none = _db([row]);
    await _repo(none).update('task-0003', const TaskPatch(extras: {'sneaky': 'x'}));
    expect(none.statements.where((s) => s.sql.startsWith('UPDATE')), isEmpty);
  });

  test('row_extras_roundtrip: every column outside the built-in set lands in extras', () {
    final row = {...rowOf(fixture('task_timed.json')), 'loan_id': 'L1', 'rank': 4, '_metadata': null, 'created_by': 'u'};
    final t = taskFromRow(row, nowUtc: now);
    expect(t.extras, {'loan_id': 'L1', 'rank': 4});
    expect(taskFromRow(rowOf(fixture('task_timed.json')), nowUtc: now).extras, isEmpty);
  });

  test('enrich_runs_in_snapshot: one read transaction, the same sql handle, names filled', () async {
    final a = {...rowOf(fixture('task_timed.json')), 'id': 'a', 'owner_user_id': 'user-1'};
    final db = _db([a], more: {'people': [{'id': 'user-1', 'name': 'Dana'}]});
    final handles = <Object>[];
    final repo = _repo(db, enricher: (sql, tasks) async {
      handles.add(sql);
      final people = await sql.getAll('SELECT * FROM people');
      return [for (final t in tasks) t.copyWith(ownerName: people.single['name'] as String?)];
    });
    final readsBefore = db.reads;
    final page = await repo.list(const TaskFilters());
    expect(page.items.single.ownerName, 'Dana');
    expect(db.reads - readsBefore, 1, reason: 'the enricher ran inside the query\'s own snapshot');
    expect(identical(handles.single, db), isFalse);
    final open = await repo.watchOpen().first;
    expect(open.single.ownerName, 'Dana');
    expect((await repo.today()).overdue.followedBy((await repo.today()).today).every((t) => t.ownerName == 'Dana'), isTrue);
    await repo.update('a', const TaskPatch(title: 'N')).then((t) => expect(t.ownerName, 'Dana'));
  });

  test('extra_watch_table_reemits: the watch listens to the extra tables too and re-reads on a pulse', () async {
    final db = _db([rowOf(fixture('task_timed.json'))], more: {'people': [{'id': 'user-1', 'name': 'Dana'}]});
    var calls = 0;
    final repo = _repo(db, watch: const ['people'], enricher: (sql, tasks) async {
      calls++;
      final name = (await sql.getAll('SELECT * FROM people')).single['name'] as String;
      return [for (final t in tasks) t.copyWith(ownerName: name)];
    });
    final seen = <String?>[];
    final sub = repo.watchOpen().listen((l) => seen.add(l.single.ownerName));
    await pumpEventQueue();
    expect(db.changeSubscriptions.single, containsAll(['tasks', 'people', 'ps_data__people']));
    db.tables['people']!.single['name'] = 'Dana R';
    db.changes.add(null);
    await pumpEventQueue();
    await sub.cancel();
    expect(seen, ['Dana', 'Dana R']);
    expect(calls, 2);
  });
}
