/// Wire enums and constants of the task contract.
library;

import 'package:bond_json/bond_json.dart';

/// `remind_minutes_before`: no reminder.
const int kRemindNone = -2;

/// `remind_minutes_before`: at the start of the day (08:00 local) of the due date.
const int kRemindMorningOf = -1;

/// The lifecycle of a task.
enum TaskStatus {
  open('open'),
  done('done'),
  cancelled('cancelled');

  const TaskStatus(this.wire);
  final String wire;

  /// A value a newer server adds reads as [open] rather than failing.
  static TaskStatus fromWire(String? s) => enumByWire(values, s, (e) => e.wire) ?? TaskStatus.open;
}

/// Where the external calendar copy of a task stands.
enum MirrorStatus {
  pending('pending'),
  mirrored('mirrored'),
  skipped('skipped'),
  failed('failed');

  const MirrorStatus(this.wire);
  final String wire;

  static MirrorStatus fromWire(String? s) => enumByWire(values, s, (e) => e.wire) ?? MirrorStatus.pending;
}
