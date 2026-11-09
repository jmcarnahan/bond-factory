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

TaskSection sectionOf(Task t, String today) {
  if (t.status != TaskStatus.open) return TaskSection.done;
  final d = t.dueDate;
  if (d == null || d.isEmpty) return TaskSection.noDate;
  if (t.overdue || d.compareTo(today) < 0) return TaskSection.overdue;
  return d == today ? TaskSection.today : TaskSection.upcoming;
}

/// "Mar 12, 9:30 AM", "Mar 12" or null for no date.
String? formatDue(Task t, BondLabels l) {
  final date = parseDueDate(t.dueDate);
  if (date == null) return null;
  final day = '${l.monthShort[date.month - 1]} ${date.day}';
  final time = parseDueTime(t.dueTime);
  if (time == null) return day;
  final h = time.hour12;
  return '$day, $h:${_two(time.minute)} ${time.isPm ? l.pm : l.am}';
}
