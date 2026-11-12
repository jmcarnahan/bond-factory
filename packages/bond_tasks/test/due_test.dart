import 'dart:convert';
import 'dart:io';

import 'package:bond_tasks/bond_tasks.dart';
import 'package:test/test.dart';

Object? _load(String name) => jsonDecode(File('../../fixtures/tasks/$name').readAsStringSync());
Task _task(String name) => Task.fromJson(_load(name) as Map<String, Object?>);

void main() {
  group('deviceDueAt', () {
    test('timed task is the local wall clock as UTC', () {
      expect(deviceDueAt('2026-03-12', '09:30'), DateTime(2026, 3, 12, 9, 30).toUtc());
      expect(deviceDueAt('2026-03-12', '09:30')!.isUtc, isTrue);
    });
    test('date-only, undated and bad strings give null', () {
      expect(deviceDueAt('2026-03-12', null), isNull);
      expect(deviceDueAt(null, '09:30'), isNull);
      expect(deviceDueAt('2026-03-12', '25:00'), isNull);
      expect(deviceDueAt('March 12', '09:30'), isNull);
      expect(deviceDueAt('2026-13-01', '09:30'), isNull);
      expect(deviceDueAt('2026-03-45', '09:30'), isNull);
      expect(deviceDueAt('2026-02-30', '09:30'), isNull);
      expect(deviceDueAt('2026-03-12', '24:00'), isNull);
    });
  });

  group('isOverdue', () {
    test('timed task flips at its due instant', () {
      final t = _task('task_overdue.json');
      final at = t.dueAt!;
      expect(isOverdue(t, at.subtract(const Duration(minutes: 1))), isFalse);
      expect(isOverdue(t, at.add(const Duration(minutes: 1))), isTrue);
    });
    test('a done task is never overdue', () {
      final t = _task('task_overdue.json').copyWith(status: TaskStatus.done);
      expect(isOverdue(t, t.dueAt!.add(const Duration(days: 3))), isFalse);
    });
    test('without dueAt the date is compared with the device local date', () {
      const t = Task(id: 'x', title: 'x', dueDate: '2026-03-12');
      expect(isOverdue(t, DateTime(2026, 3, 12, 12).toUtc()), isFalse);
      expect(isOverdue(t, DateTime(2026, 3, 13, 0, 5).toUtc()), isTrue);
    });
    test('an undated task is not overdue', () {
      expect(isOverdue(const Task(id: 'x', title: 'x'), DateTime.utc(2030)), isFalse);
    });
  });

  group('dayFor', () {
    test('date-only uses the date, timed uses the local date of dueAt', () {
      expect(dayFor(const Task(id: 'x', title: 'x', dueDate: '2026-03-12'), (u) => u), '2026-03-12');
      final t = Task(id: 'x', title: 'x', dueDate: '2026-03-12', dueTime: '23:30', dueAt: DateTime.utc(2026, 3, 13, 7, 30));
      expect(dayFor(t, (u) => u.subtract(const Duration(hours: 8))), '2026-03-12');
      expect(dayFor(t, (u) => u), '2026-03-13');
    });
    test('undated is null', () {
      expect(dayFor(const Task(id: 'x', title: 'x'), (u) => u), isNull);
    });
  });

  test('deadlineToken matches every stage_times case', () {
    final cases = (_load('stage_times.json') as List).cast<Map<String, Object?>>();
    var checked = 0;
    for (final c in cases) {
      final t = Task.fromJson(c['task'] as Map<String, Object?>);
      expect(deadlineToken(t), c['token'], reason: c['name'] as String);
      checked++;
    }
    expect(checked, greaterThan(0));
  });

  test('a timed task with unknown dueAt has an empty token', () {
    const t = Task(id: 'x', title: 'x', dueDate: '2026-03-12', dueTime: '09:30');
    expect(deadlineToken(t), '');
  });

  group('inQuietHours', () {
    const p = TaskPrefs();
    test('strictly after end and strictly before start', () {
      expect(inQuietHours(p, DateTime(2026, 3, 12, 17, 0)), isFalse);
      expect(inQuietHours(p, DateTime(2026, 3, 12, 17, 1)), isTrue);
      expect(inQuietHours(p, DateTime(2026, 3, 12, 0, 0)), isTrue);
      expect(inQuietHours(p, DateTime(2026, 3, 12, 7, 59)), isTrue);
      expect(inQuietHours(p, DateTime(2026, 3, 12, 8, 0)), isFalse);
      expect(inQuietHours(p, DateTime(2026, 3, 12, 12, 0)), isFalse);
    });
    test('a work day across midnight', () {
      const night = TaskPrefs(startOfDay: '22:00', endOfDay: '06:00');
      expect(inQuietHours(night, DateTime(2026, 3, 12, 12)), isTrue);
      expect(inQuietHours(night, DateTime(2026, 3, 12, 23)), isFalse);
    });
  });

  group('TaskTicker', () {
    test('waits to the next boundary', () {
      expect(TaskTicker.untilNextMinute(DateTime.utc(2026, 3, 12, 9, 30, 15, 500)), const Duration(seconds: 44, milliseconds: 500));
      expect(TaskTicker.untilNextMinute(DateTime.utc(2026, 3, 12, 9, 30)), const Duration(minutes: 1));
      expect(TaskTicker.untilNextDay(DateTime(2026, 3, 12, 23, 0)), const Duration(hours: 1));
    });
    test('streams are cancellable and dispose closes them', () async {
      final ticker = TaskTicker();
      final sub = ticker.minutes.listen((_) {});
      await sub.cancel();
      final done = ticker.days.listen((_) {}).asFuture<void>();
      ticker.dispose();
      await done;
    });
  });

  test('labels cover the widget strings', () {
    const l = TaskLabels();
    expect(l.priorityText(TaskPriority.high), 'High');
    expect(l.remindText(kRemindUseDefault), l.remindDefault);
    expect(const SettingsLabels().quietHoursText('08:00', '17:00'), contains('17:00 to 08:00'));
  });
}
