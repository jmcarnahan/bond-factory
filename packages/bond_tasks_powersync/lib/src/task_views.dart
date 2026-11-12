/// The day view and the badge counts, computed on the device with the server's rules.
library;

import 'package:bond_tasks/bond_tasks.dart';

DateTime _local(DateTime utc) => utc.toLocal();

String _ymd(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

/// The device's calendar date at [nowUtc].
String localToday(DateTime nowUtc) => _ymd(nowUtc.toLocal());

/// The device's local day containing [nowUtc] as `[start, end)` in UTC.
(DateTime, DateTime) localDayBounds(DateTime nowUtc) {
  final n = nowUtc.toLocal();
  return (DateTime(n.year, n.month, n.day).toUtc(), DateTime(n.year, n.month, n.day + 1).toUtc());
}

/// True when the task's day (see `dayFor`) is the device's [today] or earlier, so an open task that is
/// not overdue always lands in today or later: a date-only task dated yesterday whose due instant has
/// not passed yet is still today's work. A later day is upcoming and in no section.
bool _dayIsTodayOrEarlier(Task t, String today) {
  final day = dayFor(t, _local);
  return day != null && day.compareTo(today) <= 0;
}

/// The four exclusive sections. [open] are the user's open tasks and [done] their done tasks
/// (any day), both already decoded with `overdue` set and in the order to keep.
///
/// overdue: open and past its due instant. today: open, not overdue, its day is the device's today or earlier.
/// undated: open without a due date. doneToday: done with `completedAt` inside the local day.
TaskToday computeToday(List<Task> open, List<Task> done, DateTime nowUtc) {
  final today = localToday(nowUtc);
  final (start, end) = localDayBounds(nowUtc);
  final overdue = <Task>[], day = <Task>[], undated = <Task>[];
  for (final t in open) {
    if (isOverdue(t, nowUtc)) {
      overdue.add(t);
    } else if (t.dueDate == null) {
      undated.add(t);
    } else if (_dayIsTodayOrEarlier(t, today)) {
      day.add(t);
    }
  }
  final doneToday = [
    for (final t in done)
      if (t.completedAt != null && !t.completedAt!.isBefore(start) && t.completedAt!.isBefore(end)) t,
  ];
  return TaskToday(
    overdue: overdue,
    today: day,
    undated: undated,
    doneToday: doneToday,
    counts: TaskTodayCounts(
      overdue: overdue.length,
      today: day.length,
      undated: undated.length,
      doneToday: doneToday.length,
    ),
  );
}

/// Badge counts over the user's open tasks.
TaskSummary computeSummary(List<Task> open, DateTime nowUtc) {
  final today = localToday(nowUtc);
  var overdue = 0, dueToday = 0, noDate = 0;
  for (final t in open) {
    if (isOverdue(t, nowUtc)) {
      overdue++;
    } else if (t.dueDate == null) {
      noDate++;
    } else if (_dayIsTodayOrEarlier(t, today)) {
      dueToday++;
    }
  }
  // An overdue task without a date cannot exist; a dated overdue task is not "no date".
  return TaskSummary(open: open.length, overdue: overdue, dueToday: dueToday, noDate: noDate);
}
