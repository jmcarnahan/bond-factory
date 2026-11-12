/// Notice stages on the device and the one notice id shared by every delivery path.
library;

import 'dart:convert';

import 'package:crypto/crypto.dart';

import 'task.dart';

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

/// The notification category id registered on iOS and sent by Apple push.
const kNoticeCategory = 'bond.task';

/// The user's work day: "HH:MM" strings, minutes of lead, and how many past notices to allow.
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
  final s = _minutes(p.startOfDay);
  final e = _minutes(p.endOfDay);
  final m = local.hour * 60 + local.minute;
  if (e < s) return m > e && m < s;
  if (e == s) return false;
  return m > e || m < s;
}

int _minutes(String hhmm) {
  final parts = hhmm.split(':');
  return int.parse(parts[0]) * 60 + int.parse(parts[1]);
}

/// Stage start times of [t] in the device zone, from [nowUtc] back [pastDays] days and forward to `maxPast`.
/// Each [StageTime.sendAt] follows the quiet hours rule: the `due` stage is always sendable in its
/// 15-minute window; only past stages and the `close` stage of a date-only task are deferred to the
/// start of the work day (see [inQuietHours]).
List<StageTime> stageTimes(Task t, TaskPrefs p, DateTime nowUtc, {int pastDays = 7}) =>
    throw UnimplementedError('stageTimes is not implemented yet');

/// The stage that is current at [nowUtc], or null.
StageTime? currentStage(Task t, TaskPrefs p, DateTime nowUtc) => throw UnimplementedError('currentStage is not implemented yet');

TaskStage stageOf(Task t, TaskPrefs p, DateTime nowUtc) => throw UnimplementedError('stageOf is not implemented yet');

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
