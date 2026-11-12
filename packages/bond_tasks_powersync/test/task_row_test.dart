import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

final now = DateTime.utc(2026, 3, 11, 20);

void main() {
  test('the table declares every stored column, ints for booleans, three indexes, metadata', () {
    final t = tasksTables().single;
    expect(t.name, 'tasks');
    expect(t.columns.map((c) => c.name).toSet(), containsAll(kTaskColumns));
    expect(t.columns.length, kTaskColumns.length);
    expect(t.columns.firstWhere((c) => c.name == 'mirror_enabled').type.sqlite, 'INTEGER');
    expect(t.columns.firstWhere((c) => c.name == 'priority').type.sqlite, 'INTEGER');
    expect(t.columns.firstWhere((c) => c.name == 'checklist').type.sqlite, 'TEXT');
    expect(t.indexes.map((i) => i.columns.map((c) => c.column).toList()), [
      ['owner_user_id', 'status'],
      ['assigned_user_id', 'status'],
      ['status', 'due_at'],
    ]);
    expect(t.trackMetadata, isTrue);
  });

  for (final name in [
    'task.json',
    'task_timed.json',
    'task_overdue.json',
    'task_cancelled.json',
    'task_day_other_null_due.json',
    'task_day_self.json',
    'task_old_shape.json',
  ]) {
    test('row of $name decodes to the fixture task', () {
      final json = fixture(name);
      final expected = Task.fromJson(json);
      final got = taskFromRow(rowOf(json), nowUtc: now);
      final want = Task.fromJson({...json, 'owner_name': null, 'assignee_name': null});
      expect(got.toJson()..remove('overdue'), want.toJson()..remove('overdue'));
      expect(got.overdue, isOverdue(expected, now));
    });
  }

  test('an old-shape row (no priority, no due_at) decodes with nulls and the date fallback', () {
    final row = rowOf(fixture('task_old_shape.json'))
      ..remove('priority')
      ..remove('due_at');
    final t = taskFromRow(row, nowUtc: now);
    expect(t.priority, isNull);
    expect(t.dueAt, isNull);
    expect(t.dueDate, '2026-03-13');
    expect(t.overdue, isFalse);
    final late = taskFromRow(row, nowUtc: DateTime.utc(2026, 3, 20, 12));
    expect(late.overdue, isTrue); // dated, no due instant: the date is before the local today
  });

  test('checklist, links and booleans decode from text and ints', () {
    final row = rowOf(fixture('task_timed.json'))
      ..['checklist'] = '[{"id":"c1","text":"Print","done_at":"2026-03-10T10:00:00"}]'
      ..['mirror_enabled'] = 0;
    final t = taskFromRow(row, nowUtc: now);
    expect(t.checklist.single.text, 'Print');
    expect(t.checklist.single.doneAt, DateTime.utc(2026, 3, 10, 10)); // no Z means UTC
    expect(t.links.single.label, 'Dana Example');
    expect(t.mirrorEnabled, isFalse);
    expect(t.ownerName, isNull);
    expect(t.assigneeName, isNull);
  });

  test('a datetime without a Z is UTC', () {
    final row = rowOf(fixture('task_timed.json'))..['due_at'] = '2026-03-13T21:00:00';
    expect(taskFromRow(row, nowUtc: now).dueAt, DateTime.utc(2026, 3, 13, 21));
  });

  test('malformed JSON cells give empty lists and never throw', () {
    for (final bad in ['not json', '{"a":1}', '', '[1, "x", null]', null]) {
      final row = rowOf(fixture('task_timed.json'))
        ..['checklist'] = bad
        ..['links'] = bad;
      final t = taskFromRow(row, nowUtc: now);
      expect(t.checklist, isEmpty, reason: '$bad');
      expect(t.links, isEmpty, reason: '$bad');
    }
  });

  test('a bad datetime cell reads as null instead of throwing', () {
    final row = rowOf(fixture('task_timed.json'))..['due_at'] = 'soon';
    expect(taskFromRow(row, nowUtc: now).dueAt, isNull);
  });

  test('overdue is derived, not stored: a past due instant is overdue, a done task never', () {
    final past = rowOf(fixture('task_overdue.json'));
    expect(taskFromRow(past, nowUtc: now).overdue, isTrue);
    expect(taskFromRow({...past, 'status': 'done'}, nowUtc: now).overdue, isFalse);
    expect(taskFromRow(past, nowUtc: DateTime.utc(2000)).overdue, isFalse);
  });
}
