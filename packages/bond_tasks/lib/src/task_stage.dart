/// Notice stages on the device and the one notice id shared by every delivery path.
library;

import 'dart:convert';

import 'package:crypto/crypto.dart';

import 'task.dart';
import 'task_enums.dart';

/// Where a task stands relative to its notice stages (see [stageOf]).
///
/// A banner belongs only to [close], [due] and [past]. [upcoming] is any dated task before its first stage,
/// possibly weeks ahead, and [none] is undated, closed or finished: show nothing for those two.
enum TaskStage { none, upcoming, close, due, past }

enum NoticeAction {
  done('done'),
  snooze('snooze'),
  cancel('cancel');

  const NoticeAction(this.wire);
  final String wire;

  static NoticeAction? fromWire(String? s) {
    for (final a in values) {
      if (a.wire == s) return a;
    }
    return null;
  }
}

/// The local notification category id registered on iOS (it carries the Done, Snooze and Cancel buttons).
/// An Apple push has no category by default: its buttons show only if the app's server sends this category.
const kNoticeCategory = 'bond.task';

/// The user's work day: "HH:MM" strings, minutes of lead, and how many past notices to allow. A malformed
/// time reads as the default (start 08:00, end 17:00) wherever it is used.
class TaskPrefs {
  const TaskPrefs({this.startOfDay = '08:00', this.endOfDay = '17:00', this.leadMinutes = 60, this.maxPast = 5});

  final String startOfDay;
  final String endOfDay;
  final int leadMinutes;
  final int maxPast;
}

/// One scheduled stage: [stage] is `close`, `due` or `past`; [last] marks the final past notice.
class StageTime {
  const StageTime({required this.stage, required this.seq, required this.at, this.last = false, this.sendAt});

  final String stage;
  final int seq;

  /// When the stage starts.
  final DateTime at;
  final bool last;

  /// When the notice is actually sent: [at], or deferred to the start of the work day when [at] falls
  /// in quiet hours; null when a later notice supersedes it. The `due` stage is always sent in its
  /// 15-minute window (timed and date-only); quiet hours defer only past stages and the `close` stage
  /// of a date-only task.
  final DateTime? sendAt;
}

/// True when [local] (a device local time) is strictly after `endOfDay` and strictly before
/// `startOfDay`; the two times themselves are not quiet. With a work day across midnight
/// the quiet hours sit inside one day; equal times mean no quiet hours.
bool inQuietHours(TaskPrefs p, DateTime local) {
  final s = _minutes(p.startOfDay, 8 * 60);
  final e = _minutes(p.endOfDay, 17 * 60);
  final m = local.hour * 60 + local.minute;
  if (e < s) return m > e && m < s;
  if (e == s) return false;
  return m > e || m < s;
}

final RegExp _hhmm = RegExp(r'^(\d{1,2}):(\d{2})$');

/// Minutes after midnight of an "HH:MM" string. A malformed or out-of-range value (a server can send
/// anything) gives [fallback] instead of throwing inside a build method or the alert sync.
int _minutes(String hhmm, int fallback) {
  final m = _hhmm.firstMatch(hhmm.trim());
  if (m == null) return fallback;
  final h = int.parse(m[1]!), min = int.parse(m[2]!);
  return h > 23 || min > 59 ? fallback : h * 60 + min;
}

/// The schedule of [t] for a recipient of every stage (close, due and past), in the device zone.
///
/// `close` starts at `dueAt` minus the lead; `due` at `dueAt`; `past` seq 0 at `dueAt` + 15 minutes and
/// seq k >= 1 at `startOfDay` on the due local date + k days (calendar days, never 24-hour blocks). Local
/// wall times are built with `DateTime(y, m, d, h, min)`. Each [StageTime.sendAt] follows the quiet hours
/// rule: `due` and the `close` of a timed task are always sent at their time; past stages and the `close`
/// of a date-only task move to the next start of the work day if still current then, else null.
/// Stages starting more than [pastDays] before [nowUtc] are left out; later ones are all listed.
///
/// An undated or closed task, or a timed task whose `dueAt` is unknown, gives `[]`. A date-only task with
/// no `dueAt` is scheduled from the device's `endOfDay` of its date.
List<StageTime> stageTimes(Task t, TaskPrefs p, DateTime nowUtc, {int pastDays = 7}) =>
    _trim(_plan(t, p, _Role.every), nowUtc, pastDays);

/// The schedule of [t] for [userId], who is on this device. Close and due go to the responsible user
/// (assignee, else owner); past goes to them and to the owner. Anyone else gets `[]`.
///
/// Documented limit: for a date-only task of another user whose `dueAt` is unknown the device does not
/// know that user's end of day, so only the morning stages (seq 1 and up) are listed.
List<StageTime> stageTimesFor(Task t, TaskPrefs p, DateTime nowUtc, {required String userId, int pastDays = 7}) {
  final role = _roleOf(t, userId);
  return role == null ? const [] : _trim(_plan(t, p, role), nowUtc, pastDays);
}

/// The stage that is current at [nowUtc], or null: close from its start to `dueAt`, due for 15 minutes,
/// then past until the next one; the last past stage ends at the morning after it. With [userId] the
/// schedule is that user's ([stageTimesFor]).
StageTime? currentStage(Task t, TaskPrefs p, DateTime nowUtc, {String? userId}) {
  final plan = _planFor(t, p, userId);
  if (plan == null || plan.stages.isEmpty || !nowUtc.isBefore(plan.end)) return null;
  StageTime? cur;
  for (final s in plan.stages) {
    if (s.at.isAfter(nowUtc)) break;
    cur = s;
  }
  return cur;
}

/// What a banner shows: `upcoming` for a dated task before its first stage, else the current stage's
/// kind, else `none` (undated, closed, unknown `dueAt`, or after the last stage).
TaskStage stageOf(Task t, TaskPrefs p, DateTime nowUtc, {String? userId}) {
  final plan = _planFor(t, p, userId);
  if (plan == null || plan.stages.isEmpty) return TaskStage.none;
  if (nowUtc.isBefore(plan.stages.first.at)) return TaskStage.upcoming;
  return switch (currentStage(t, p, nowUtc, userId: userId)?.stage) {
    'close' => TaskStage.close,
    'due' => TaskStage.due,
    'past' => TaskStage.past,
    _ => TaskStage.none,
  };
}

/// True when the current stage may be claimed at [nowUtc]: its [StageTime.sendAt] has come, and either it
/// is exempt from quiet hours (`due`, or `close` of a timed task) or [nowUtc] is not in quiet hours.
bool isSendableNow(Task t, TaskPrefs p, DateTime nowUtc, {String? userId}) {
  final c = currentStage(t, p, nowUtc, userId: userId);
  final at = c?.sendAt;
  if (c == null || at == null || at.isAfter(nowUtc)) return false;
  if (c.stage == 'due' || (c.stage == 'close' && t.dueTime != null)) return true;
  return !inQuietHours(p, nowUtc.toLocal());
}

/// A stored lead above this is accepted on input and counts as this when used.
const int kMaxLeadMinutes = 10080;

enum _Role { every, responsible, ownerOnly }

_Role? _roleOf(Task t, String userId) {
  if (userId.isEmpty) return null;
  final responsible = (t.assignedUserId ?? '').isNotEmpty ? t.assignedUserId! : t.ownerUserId;
  if (userId == responsible) return _Role.responsible;
  return userId == t.ownerUserId ? _Role.ownerOnly : null;
}

class _Plan {
  const _Plan(this.stages, this.end);
  final List<StageTime> stages;

  /// When the last stage stops being current.
  final DateTime end;
}

_Plan? _planFor(Task t, TaskPrefs p, String? userId) {
  if (userId == null) return _plan(t, p, _Role.every);
  final role = _roleOf(t, userId);
  return role == null ? null : _plan(t, p, role);
}

List<StageTime> _trim(_Plan? plan, DateTime nowUtc, int pastDays) {
  if (plan == null) return const [];
  final from = nowUtc.subtract(Duration(days: pastDays));
  return [
    for (final s in plan.stages)
      if (!s.at.isBefore(from)) s,
  ];
}

final RegExp _ymd = RegExp(r'^(\d{4})-(\d{2})-(\d{2})$');

_Plan? _plan(Task t, TaskPrefs p, _Role role) {
  final date = t.dueDate;
  if (!t.isOpen || date == null) return null;
  final match = _ymd.firstMatch(date);
  if (match == null) return null;
  final timed = t.dueTime != null;
  final sod = _minutes(p.startOfDay, 8 * 60);
  DateTime atClock(int y, int m, int d, int minutes) => DateTime(y, m, d, minutes ~/ 60, minutes % 60).toUtc();

  var y = int.parse(match[1]!), m = int.parse(match[2]!), d = int.parse(match[3]!);
  var dueAt = t.dueAt;
  if (timed && dueAt == null) return null; // no stages until the server's dueAt arrives
  if (dueAt != null) {
    // The due local date, as the server counts it, for the morning slots and the morning close. For a
    // date-only task written in another zone this can differ from the dueDate string.
    final l = dueAt.toLocal();
    y = l.year;
    m = l.month;
    d = l.day;
  } else if (role != _Role.ownerOnly) {
    dueAt = atClock(y, m, d, _minutes(p.endOfDay, 17 * 60)); // date-only, dueAt unknown: the device's end of day
  }
  DateTime morning(int k) => atClock(y, m, d + k, sod);

  final raw = <(String, int, DateTime)>[];
  if (dueAt != null && role != _Role.ownerOnly) {
    final closeAt = _closeAt(t, p, dueAt, morning(0));
    if (closeAt != null) raw.add(('close', 0, closeAt));
    raw.add(('due', 0, dueAt));
  }
  if (dueAt != null) {
    final first = dueAt.add(const Duration(minutes: 15));
    if (first.isBefore(morning(1))) raw.add(('past', 0, first));
  }
  for (var k = 1; k <= p.maxPast; k++) {
    raw.add(('past', k, morning(k)));
  }

  final end = morning(p.maxPast + 1);
  final stages = <StageTime>[];
  for (var i = 0; i < raw.length; i++) {
    final (stage, seq, at) = raw[i];
    final stop = i + 1 < raw.length ? raw[i + 1].$3 : end;
    final exempt = stage == 'due' || (stage == 'close' && timed);
    var sendAt = at as DateTime?;
    if (!exempt && inQuietHours(p, at.toLocal())) {
      final next = _nextStart(at, sod);
      sendAt = next.isBefore(stop) ? next : null;
    }
    stages.add(StageTime(stage: stage, seq: seq, at: at, last: stage == 'past' && seq == p.maxPast, sendAt: sendAt));
  }
  return _Plan(stages, end);
}

DateTime? _closeAt(Task t, TaskPrefs p, DateTime dueAt, DateTime morning) {
  final n = t.remindMinutesBefore;
  if (n == kRemindMorningOf) return morning.isBefore(dueAt) ? morning : null;
  final int lead;
  if (n == kRemindUseDefault) {
    lead = p.leadMinutes;
  } else if (n >= 0) {
    lead = n;
  } else {
    return null; // kRemindNone and any other negative value: no close stage
  }
  final capped = lead < kMaxLeadMinutes ? lead : kMaxLeadMinutes;
  return capped <= 0 ? null : dueAt.subtract(Duration(minutes: capped));
}

/// The first `startOfDay` instant strictly after [at].
DateTime _nextStart(DateTime at, int sod) {
  final l = at.toLocal();
  var c = DateTime(l.year, l.month, l.day, sod ~/ 60, sod % 60);
  if (!c.isAfter(l)) c = DateTime(l.year, l.month, l.day + 1, sod ~/ 60, sod % 60);
  return c.toUtc();
}

/// The part of a notice id that changes when the deadline moves: `dueAt` in epoch minutes for a
/// timed task, the ISO `dueDate` for a date-only task, and an empty string for an undated task.
/// A timed task whose `dueAt` is not known yet also gives an empty string (it has no stages until the
/// server's `dueAt` arrives; falling back to the date would change the id later and notify twice).
String deadlineToken(Task t) {
  if (t.dueDate == null) return '';
  if (t.dueTime != null) {
    final at = t.dueAt;
    return at == null ? '' : (at.millisecondsSinceEpoch ~/ 60000).toString();
  }
  return t.dueDate!;
}

/// The notice id: `sha256("task|user|stage|seq|token")` as hex, first 32 characters.
String noticeId(String taskId, String userId, String stage, int seq, String token) =>
    sha256.convert(utf8.encode('$taskId|$userId|$stage|$seq|$token')).toString().substring(0, 32);

/// FNV-1a 32-bit over the UTF-8 bytes, masked to 31 bits (the local notification id).
int fnv1a31(String s) {
  // The product is split into 16-bit halves: on the web an int is a double, and h * prime would pass 2^53.
  var h = 0x811c9dc5;
  for (final b in utf8.encode(s)) {
    h ^= b;
    final lo = (h & 0xFFFF) * 0x01000193;
    final hi = (((h >> 16) & 0xFFFF) * 0x0193) & 0xFFFF; // only the low 16 bits of hi * prime survive << 16
    h = (lo + hi * 0x10000) & 0xFFFFFFFF;
  }
  return h & 0x7FFFFFFF;
}
