import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:powersync/powersync.dart' show Column, Index, IndexedColumn;

import 'support.dart';

void main() {
  final bad = ['status', 'created_by', 'Title', 'x y', 'a;b', 'STATUS', 'id', '_metadata', 'due_date', '1a', '', 'a"b'];

  test('tasks_tables_rejects_unsafe_and_clashing_column_names', () {
    for (final n in bad) {
      expect(() => tasksTables(extraColumns: [Column.text(n)]), throwsArgumentError, reason: n);
    }
    expect(tasksTables(extraColumns: [const Column.text('loan_id'), const Column.text('_x9')]), isNotEmpty);
  });

  test('tasks_tables_rejects_extra_index_clash_with_built_in', () {
    for (final n in ['owner_status', 'Status_Due', 'assignee_status']) {
      expect(() => tasksTables(extraIndexes: [Index(n, const [IndexedColumn('status')])]), throwsArgumentError, reason: n);
    }
    expect(
        () => tasksTables(extraIndexes: [
              const Index('a', [IndexedColumn('status')]),
              const Index('a', [IndexedColumn('status')])
            ]),
        throwsArgumentError);
  });

  test('repository_rejects_unsafe_and_clashing_extra_columns', () {
    final db = fakeTasks([]);
    for (final n in bad) {
      expect(() => PowerSyncTaskRepository(db, userId: 'u', extraColumns: {n}), throwsArgumentError, reason: n);
    }
    expect(PowerSyncTaskRepository(db, userId: 'u', extraColumns: const {'loan_id'}), isNotNull);
  });

  test('enricher_wrong_length_is_a_clear_state_error', () async {
    final a = {...rowOf(fixture('task_timed.json')), 'id': 'a', 'owner_user_id': 'user-1'};
    final db = fakeTasks([a]);
    final repo = PowerSyncTaskRepository(db,
        userId: 'user-1',
        clock: TaskClock(() => DateTime.utc(2026, 3, 11, 20)),
        enricher: (sql, tasks) async => [...tasks, tasks.first]);
    await expectLater(
        repo.list(const TaskFilters()),
        throwsA(isA<StateError>().having((e) => e.message, 'message', allOf(contains('2'), contains('1')))));
  });
}
