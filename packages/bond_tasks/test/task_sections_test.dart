import 'package:bond_tasks/bond_tasks.dart';
import 'package:test/test.dart';

Task _t(String id, {String? date, String? time, DateTime? dueAt, TaskStatus status = TaskStatus.open}) =>
    Task(id: id, title: id, dueDate: date, dueTime: time, dueAt: dueAt, status: status, ownerUserId: 'u');

void main() {
  // 2026-03-12 10:00 UTC is the 12th in every zone from UTC-10 to UTC+13.
  final now = DateTime.utc(2026, 3, 12, 10);
  List<String> ids(List<Task> l) => [for (final t in l) t.id];

  test('a date-only task dated yesterday whose due instant is still ahead stays under today', () {
    final s = sectionTasks([_t('y', date: '2026-03-11', dueAt: DateTime.utc(2026, 3, 13, 6))], now);
    expect(ids(s.today), ['y']);
    expect(s.overdue, isEmpty);
    expect(s.today.single.overdue, isFalse);
    expect(s.counts.today, 1);
  });

  test('a task whose due instant passed is overdue, even if its date is today', () {
    final s = sectionTasks([_t('p', date: '2026-03-12', time: '09:00', dueAt: DateTime.utc(2026, 3, 12, 9, 59))], now);
    expect(ids(s.overdue), ['p']);
    expect(s.overdue.single.overdue, isTrue);
    expect(s.today, isEmpty);
  });

  test('a later day is upcoming, in no section; no date is undated; closed tasks are ignored', () {
    final s = sectionTasks([
      _t('later', date: '2026-03-13'),
      _t('free'),
      _t('done', date: '2026-03-12', status: TaskStatus.done),
    ], now);
    expect([ids(s.overdue), ids(s.today), ids(s.undated)], [<String>[], <String>[], ['free']]);
    expect(s.counts.undated, 1);
  });

  test('sections are ordered by dueAt, nulls last, then the given order; no task is in two', () {
    final s = sectionTasks([
      _t('n1', date: '2026-03-12'),
      _t('late', date: '2026-03-12', time: '20:00', dueAt: DateTime.utc(2026, 3, 12, 20)),
      _t('n2', date: '2026-03-12'),
      _t('soon', date: '2026-03-12', time: '11:00', dueAt: DateTime.utc(2026, 3, 12, 11)),
      _t('late', date: '2026-03-12', time: '20:00', dueAt: DateTime.utc(2026, 3, 12, 20)),
    ], now);
    expect(ids(s.today), ['soon', 'late', 'n1', 'n2']);
  });

  test('done tasks and their count are carried over', () {
    final d = _t('d', date: '2026-03-12', status: TaskStatus.done);
    final s = sectionTasks([_t('a', date: '2026-03-12')], now, doneToday: [d], doneTodayCount: 7);
    expect(ids(s.doneToday), ['d']);
    expect(s.counts.doneToday, 7);
  });
}
