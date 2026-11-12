/// Client side due-instant rules: the device's due instant, the overdue test and a task's day.
library;

import 'task.dart';

final RegExp _date = RegExp(r'^(\d{4})-(\d{2})-(\d{2})$');
final RegExp _time = RegExp(r'^(\d{1,2}):(\d{2})$');

/// The due instant of a timed task in the device's own zone: the local wall clock `dueDate` and
/// `dueTime` converted to UTC. Null for a date-only task (the server decides its end-of-day
/// instant), for no date, or when the strings do not parse.
DateTime? deviceDueAt(String? dueDate, String? dueTime) {
  if (dueDate == null || dueTime == null) return null;
  final d = _date.firstMatch(dueDate);
  final t = _time.firstMatch(dueTime);
  if (d == null || t == null) return null;
  final y = int.parse(d[1]!);
  final mo = int.parse(d[2]!);
  final day = int.parse(d[3]!);
  final h = int.parse(t[1]!);
  final min = int.parse(t[2]!);
  if (h > 23 || min > 59 || mo < 1 || mo > 12 || day < 1) return null;
  // A day past the end of the month would roll over; reject it instead.
  if (day > DateTime(y, mo + 1, 0).day) return null;
  return DateTime(y, mo, day, h, min).toUtc();
}

/// A task is overdue when it is open and its due instant has passed. A dated task whose `dueAt`
/// is not known yet falls back to its `dueDate` being before the device's local date.
bool isOverdue(Task t, DateTime nowUtc) {
  if (!t.isOpen) return false;
  final at = t.dueAt;
  if (at != null) return at.isBefore(nowUtc);
  final day = t.dueDate;
  if (day == null) return false;
  return day.compareTo(_iso(nowUtc.toLocal())) < 0;
}

/// The task's calendar day (`YYYY-MM-DD`) for the viewer: `dueDate` for a date-only task, else the
/// date of `dueAt` after [toLocal]. Null for an undated task.
String? dayFor(Task t, DateTime Function(DateTime utc) toLocal) {
  if (t.dueDate == null) return null;
  final at = t.dueAt;
  if (t.dueTime == null || at == null) return t.dueDate;
  return _iso(toLocal(at));
}

String _iso(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
