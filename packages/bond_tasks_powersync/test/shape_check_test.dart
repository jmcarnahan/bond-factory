import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';

import 'shape_support.dart';

void bad(TaskTableShape s, [Set<String> extras = const {}]) => expect(() => s.check(extras), throwsArgumentError);

void main() {
  test('the legacy shape is accepted, and so is the default one', () {
    legacyShape.check(legacyExtras);
    const TaskTableShape().check(const {});
    expect(legacyShape.dueOrder, TaskDueOrder.dateThenTime);
    expect(const TaskTableShape().dueOrder, TaskDueOrder.dueAt);
    expect(const TaskTableShape(dueOrder: TaskDueOrder.dateThenTime).dueOrder, TaskDueOrder.dateThenTime);
    expect(legacyShape.local('mirror_enabled'), 'sync_to_calendar');
    expect(legacyShape.local('title'), 'title');
    expect(legacyShape.has('priority'), isFalse);
    expect(legacyShape.has('title'), isTrue);
    // a rename to its own name is a no-op, not a clash
    const TaskTableShape(rename: {'title': 'title'}).check(const {});
  });

  test('absent and rename keys must be module columns', () {
    bad(const TaskTableShape(absent: {'nope'}));
    bad(const TaskTableShape(rename: {'nope': 'x'}));
    bad(const TaskTableShape(absent: {'id'}));
  });

  test('the columns the rules need cannot be absent', () {
    for (final c in ['owner_user_id', 'assigned_user_id', 'title', 'status', 'due_date', 'due_time', 'completed_at', 'created_at', 'updated_at']) {
      bad(TaskTableShape(absent: {c}));
    }
  });

  test('a renamed column may not also be absent', () {
    bad(const TaskTableShape(absent: {'priority'}, rename: {'priority': 'prio'}));
  });

  test('local names must be safe, unreserved and unique', () {
    bad(const TaskTableShape(rename: {'priority': 'Prio'}));
    bad(const TaskTableShape(rename: {'priority': 'a b'}));
    bad(const TaskTableShape(rename: {'priority': 'x; DROP TABLE tasks'}));
    bad(const TaskTableShape(rename: {'priority': 'id'}));
    bad(const TaskTableShape(rename: {'priority': '_metadata'}));
    bad(const TaskTableShape(rename: {'priority': 'title'})); // another module column
    bad(const TaskTableShape(rename: {'priority': 'client_ref'}), {'client_ref'}); // an extra column
    bad(const TaskTableShape(rename: {'priority': 'p', 'source': 'p'})); // used twice
    const TaskTableShape(rename: {'priority': 'prio'}).check(const {});
  });

  test('dueOrder dueAt needs due_at', () {
    bad(const TaskTableShape(absent: {'due_at'}, dueOrder: TaskDueOrder.dueAt));
    const TaskTableShape(absent: {'due_at'}, dueOrder: TaskDueOrder.dateThenTime).check(const {});
  });

  test('the repository constructor runs the check', () {
    expect(() => legacyRepo(legacyDb([]), shape: const TaskTableShape(absent: {'title'})), throwsArgumentError);
    expect(() => legacyRepo(legacyDb([]), extraColumns: {'client_ref', 'sync_to_calendar'}), throwsArgumentError);
  });
}
