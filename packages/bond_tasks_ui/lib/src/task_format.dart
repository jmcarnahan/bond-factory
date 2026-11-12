/// Date, time and section helpers shared by the task widgets.
library;

import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';

String _two(int n) => n.toString().padLeft(2, '0');

/// `YYYY-MM-DD` of the calendar day of [d] (its own fields, no zone shift).
String dueDateString(DateTime d) => '${d.year.toString().padLeft(4, '0')}-${_two(d.month)}-${_two(d.day)}';

/// The wall date of a `YYYY-MM-DD` string as local midnight; null when empty or malformed.
DateTime? parseDueDate(String? s) {
  if (s == null) return null;
  final m = RegExp(r'^(\d{4})-(\d{2})-(\d{2})$').firstMatch(s);
  if (m == null) return null;
  final y = int.parse(m[1]!);
  final mo = int.parse(m[2]!);
  final d = int.parse(m[3]!);
  final date = DateTime(y, mo, d);
  // 2026-13-45 would roll over into a real day; treat it as unreadable.
  return date.year == y && date.month == mo && date.day == d ? date : null;
}

/// `HH:MM` as a time of day; null when empty or malformed.
BondTime? parseDueTime(String? s) {
  if (s == null) return null;
  final m = RegExp(r'^(\d{1,2}):(\d{2})$').firstMatch(s);
  if (m == null) return null;
  final h = int.parse(m[1]!);
  final min = int.parse(m[2]!);
  if (h > 23 || min > 59) return null;
  return BondTime(hour24: h, minute: min);
}

String dueTimeString(BondTime t) => '${_two(t.hour24)}:${_two(t.minute)}';

/// Which list section a task belongs to, judged against [today] (`YYYY-MM-DD`).
enum TaskSection { overdue, today, upcoming, noDate, done }

///
/// With [now] the answer is exactly `sectionTasks`' (`bond_tasks`): overdue by
/// `isOverdue`, else today when the viewer's day (`dayFor`) is today or earlier,
/// else upcoming; [today] is then taken from [now]. Without [now] the task's
/// own `overdue` flag and a date before [today] decide.
TaskSection sectionOf(Task t, String today, {DateTime? now}) {
  if (t.status != TaskStatus.open) return TaskSection.done;
  final d = t.dueDate;
  if (d == null || d.isEmpty) return TaskSection.noDate;
  if (now != null) {
    // The one rule: the same function the day view uses (`sectionTasks`).
    final s = sectionTasks([t], now);
    if (s.overdue.isNotEmpty) return TaskSection.overdue;
    if (s.today.isNotEmpty) return TaskSection.today;
    if (s.undated.isNotEmpty) return TaskSection.noDate;
    return TaskSection.upcoming;
  }
  if (t.overdue || d.compareTo(today) < 0) return TaskSection.overdue;
  return d == today ? TaskSection.today : TaskSection.upcoming;
}

/// "9:30 AM" for a local time.
String formatTimeOfDay(DateTime local, BondLabels l) {
  final h = local.hour % 12 == 0 ? 12 : local.hour % 12;
  return '$h:${_two(local.minute)} ${local.hour >= 12 ? l.pm : l.am}';
}

/// "Mar 12, 9:30 AM", "Mar 12" or null for no date. A timed task that has its
/// due instant shows that instant in the device's zone.
String? formatDue(Task t, BondLabels l) {
  final date = parseDueDate(t.dueDate);
  if (date == null) return null;
  final at = t.dueAt;
  if (at != null && parseDueTime(t.dueTime) != null) {
    final local = at.toLocal();
    return '${l.monthShort[local.month - 1]} ${local.day}, ${formatTimeOfDay(local, l)}';
  }
  final day = '${l.monthShort[date.month - 1]} ${date.day}';
  final time = parseDueTime(t.dueTime);
  if (time == null) return day;
  final h = time.hour12;
  return '$day, $h:${_two(time.minute)} ${time.isPm ? l.pm : l.am}';
}
