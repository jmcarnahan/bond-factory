import 'dart:convert';
import 'dart:io';

import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:flutter_test/flutter_test.dart';

/// `sectionOf(now: ...)` must give the answer `sectionTasks` (the day view) gives, for every task.
void main() {
  final files = [
    'task.json',
    'task_cancelled.json',
    'task_timed.json',
    'task_day_self.json',
    'task_day_other_null_due.json',
    'task_overdue.json',
    'task_old_shape.json',
  ];
  final tasks = [
    for (final f in files)
      Task.fromJson(jsonDecode(File('../../fixtures/tasks/$f').readAsStringSync()) as Map<String, Object?>),
    // Shapes the fixtures may not cover: a date-only task dated yesterday whose instant is ahead, a far-ahead
    // task, an undated task and a timed task today.
    Task(id: 'y', title: 'y', dueDate: '2026-03-11', dueAt: DateTime(2026, 3, 12, 20).toUtc()),
    const Task(id: 'f', title: 'f', dueDate: '2027-01-01'),
    const Task(id: 'u', title: 'u'),
    Task(id: 't', title: 't', dueDate: '2026-03-12', dueTime: '17:00', dueAt: DateTime(2026, 3, 12, 17).toUtc()),
  ];
  final instants = [DateTime(2026, 3, 12, 6), DateTime(2026, 3, 12, 17, 1), DateTime(2026, 3, 14, 12).toUtc()];

  TaskSection viaDayView(Task t, DateTime now) {
    if (!t.isOpen) return TaskSection.done;
    final s = sectionTasks([t], now.toUtc());
    if (s.overdue.isNotEmpty) return TaskSection.overdue;
    if (s.today.isNotEmpty) return TaskSection.today;
    if (s.undated.isNotEmpty) return TaskSection.noDate;
    return TaskSection.upcoming;
  }

  for (final now in instants) {
    test('sectionOf agrees with sectionTasks for every task at $now', () {
      final local = now.toLocal();
      final today = dueDateString(DateTime(local.year, local.month, local.day));
      for (final t in tasks) {
        expect(sectionOf(t, today, now: now), viaDayView(t, now), reason: '${t.id} at $now');
      }
    });
  }

  test('the old stale-flag rule is not used with now', () {
    final t = Task(id: 'x', title: 'x', dueDate: '2026-03-12', dueTime: '17:00', dueAt: DateTime(2026, 3, 12, 17).toUtc(), overdue: true);
    expect(sectionOf(t, '2026-03-12', now: DateTime(2026, 3, 12, 6)), TaskSection.today);
  });
}
