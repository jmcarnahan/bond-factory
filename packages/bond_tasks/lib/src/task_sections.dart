/// The day view's sections, derived on the device from the open tasks and the clock.
library;

import 'task.dart';
import 'task_due.dart';
import 'task_today.dart';

/// Splits [open] into the day view's exclusive sections as of [nowUtc] (the device zone is the viewer's):
/// - `overdue`: the task's due instant has passed ([isOverdue]);
/// - `undated`: no due date;
/// - `today`: every other task whose day ([dayFor]) is the viewer's today or earlier, so a date-only task
///   dated yesterday whose due instant is still ahead (another zone) is not lost;
/// - a task on a later day is in no section (it is "upcoming").
///
/// Each section is ordered by `dueAt` ascending, nulls last, then the order of [open]. `overdue` is set
/// on every returned task. Tasks that are not open are ignored. Counts are the section lengths;
/// [doneToday] and [doneTodayCount] are carried over.
TaskToday sectionTasks(
  Iterable<Task> open,
  DateTime nowUtc, {
  List<Task> doneToday = const [],
  int? doneTodayCount,
}) {
  final local = nowUtc.toLocal();
  final today = '${local.year.toString().padLeft(4, '0')}-${local.month.toString().padLeft(2, '0')}-'
      '${local.day.toString().padLeft(2, '0')}';
  final overdue = <Task>[], todays = <Task>[], undated = <Task>[];
  final seen = <String>{};
  for (final raw in open) {
    if (!raw.isOpen || !seen.add(raw.id)) continue;
    final o = isOverdue(raw, nowUtc);
    final t = o == raw.overdue ? raw : raw.copyWith(overdue: o);
    if (o) {
      overdue.add(t);
    } else if (t.dueDate == null) {
      undated.add(t);
    } else if ((dayFor(t, (u) => u.toLocal()) ?? t.dueDate!).compareTo(today) <= 0) {
      todays.add(t);
    }
  }
  return TaskToday(
    overdue: _byDue(overdue),
    today: _byDue(todays),
    undated: undated,
    doneToday: doneToday,
    counts: TaskTodayCounts(
      overdue: overdue.length,
      today: todays.length,
      undated: undated.length,
      doneToday: doneTodayCount ?? doneToday.length,
    ),
  );
}

List<Task> _byDue(List<Task> l) {
  final idx = {for (var i = 0; i < l.length; i++) l[i].id: i};
  return [...l]..sort((a, b) {
      final x = a.dueAt, y = b.dueAt;
      if (x != null && y != null) {
        final c = x.compareTo(y);
        if (c != 0) return c;
      } else if (x != null || y != null) {
        return x == null ? 1 : -1;
      }
      return idx[a.id]!.compareTo(idx[b.id]!);
    });
}
