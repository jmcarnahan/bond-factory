import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter_test/flutter_test.dart';

final DateTime _now = DateTime(2026, 3, 12, 12);

void main() {
  const l = BondLabels.defaults;

  group('formatDue', () {
    test('date only, wall time and no date', () {
      expect(formatDue(const Task(id: 'a', title: 't', dueDate: '2026-03-12'), l), 'Mar 12');
      expect(formatDue(const Task(id: 'a', title: 't', dueDate: '2026-03-12', dueTime: '09:30'), l), 'Mar 12, 9:30 AM');
      expect(formatDue(const Task(id: 'a', title: 't'), l), isNull);
    });

    test('a timed task with its instant shows that instant in the device zone', () {
      // 14:05 local, built through the device zone so the test holds in any zone.
      final at = DateTime(2026, 3, 12, 14, 5).toUtc();
      final t = Task(id: 'a', title: 't', dueDate: '2026-03-12', dueTime: '09:30', dueAt: at);
      expect(formatDue(t, l), 'Mar 12, 2:05 PM', reason: 'the instant wins over the sender wall clock');
    });

    test('midnight and noon read 12', () {
      expect(formatTimeOfDay(DateTime(2026, 3, 12, 0, 7), l), '12:07 AM');
      expect(formatTimeOfDay(DateTime(2026, 3, 12, 12, 0), l), '12:00 PM');
    });

    test('a date-only task ignores a dueAt (its end-of-day instant is not a time)', () {
      final t = Task(id: 'a', title: 't', dueDate: '2026-03-12', dueAt: DateTime(2026, 3, 12, 23, 59).toUtc());
      expect(formatDue(t, l), 'Mar 12');
    });
  });

  group('sectionOf', () {
    test('without now it keeps the flag and the date rule', () {
      expect(sectionOf(const Task(id: 'a', title: 't', dueDate: '2026-03-11'), '2026-03-12'), TaskSection.overdue);
      expect(sectionOf(const Task(id: 'a', title: 't', dueDate: '2026-03-12', overdue: true), '2026-03-12'), TaskSection.overdue);
      expect(sectionOf(const Task(id: 'a', title: 't', dueDate: '2026-03-12'), '2026-03-12'), TaskSection.today);
    });

    test('with now a timed task past its instant is overdue the same day', () {
      final past = Task(id: 'a', title: 't', dueDate: '2026-03-12', dueTime: '08:00', dueAt: DateTime(2026, 3, 12, 8).toUtc());
      final later = Task(id: 'a', title: 't', dueDate: '2026-03-12', dueTime: '17:00', dueAt: DateTime(2026, 3, 12, 17).toUtc());
      expect(sectionOf(past, '2026-03-12', now: _now), TaskSection.overdue);
      expect(sectionOf(later, '2026-03-12', now: _now), TaskSection.today);
      expect(isOverdue(past, _now), isTrue, reason: 'the same rule as the model');
    });

    test('with now a stale overdue flag does not decide', () {
      final t = Task(id: 'a', title: 't', dueDate: '2026-03-12', dueTime: '17:00', dueAt: DateTime(2026, 3, 12, 17).toUtc(), overdue: true);
      expect(sectionOf(t, '2026-03-12', now: _now), TaskSection.today);
    });

    test('done, undated and upcoming', () {
      expect(sectionOf(const Task(id: 'a', title: 't', status: TaskStatus.done), '2026-03-12', now: _now), TaskSection.done);
      expect(sectionOf(const Task(id: 'a', title: 't'), '2026-03-12', now: _now), TaskSection.noDate);
      expect(sectionOf(const Task(id: 'a', title: 't', dueDate: '2026-03-13'), '2026-03-12', now: _now), TaskSection.upcoming);
    });
  });
}
