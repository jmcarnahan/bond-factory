/// Minute and day ticks, so overdue flags and the day view never go stale.
library;

import 'dart:async';

import 'task_clock.dart';

class TaskTicker {
  TaskTicker({TaskClock clock = const TaskClock()}) : _clock = clock {
    _minutes = StreamController<DateTime>.broadcast(
      onListen: () => _arm(_minuteTimer, true),
      onCancel: () => _disarm(true),
    );
    _days = StreamController<DateTime>.broadcast(
      onListen: () => _arm(_dayTimer, false),
      onCancel: () => _disarm(false),
    );
  }

  final TaskClock _clock;
  late final StreamController<DateTime> _minutes;
  late final StreamController<DateTime> _days;
  Timer? _minuteTimer;
  Timer? _dayTimer;
  bool _disposed = false;

  /// Time left until the next minute boundary after [now] (always more than zero).
  static Duration untilNextMinute(DateTime now) =>
      const Duration(minutes: 1) - Duration(seconds: now.second, milliseconds: now.millisecond, microseconds: now.microsecond);

  /// Time left until the next local midnight after [nowLocal].
  static Duration untilNextDay(DateTime nowLocal) =>
      DateTime(nowLocal.year, nowLocal.month, nowLocal.day + 1).difference(nowLocal);

  /// Emits the current UTC time at every minute boundary.
  Stream<DateTime> get minutes => _minutes.stream;

  /// Emits the current UTC time when the local calendar day changes.
  Stream<DateTime> get days => _days.stream;

  void _arm(Timer? existing, bool minute) {
    if (_disposed) return;
    existing?.cancel();
    final now = _clock.nowLocal();
    final wait = minute ? untilNextMinute(now) : untilNextDay(now);
    final timer = Timer(wait, () {
      if (_disposed) return;
      final c = minute ? _minutes : _days;
      if (!c.hasListener) return;
      c.add(_clock.nowUtc());
      _arm(null, minute);
    });
    if (minute) {
      _minuteTimer = timer;
    } else {
      _dayTimer = timer;
    }
  }

  void _disarm(bool minute) {
    if (minute) {
      _minuteTimer?.cancel();
      _minuteTimer = null;
    } else {
      _dayTimer?.cancel();
      _dayTimer = null;
    }
  }

  /// Stops both timers and closes both streams.
  void dispose() {
    _disposed = true;
    _minuteTimer?.cancel();
    _dayTimer?.cancel();
    _minutes.close();
    _days.close();
  }
}
