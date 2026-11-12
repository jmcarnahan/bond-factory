/// An injectable "now", so tests and the ticker control time.
library;

class TaskClock {
  const TaskClock([DateTime Function()? now]) : _now = now;

  final DateTime Function()? _now;

  DateTime nowUtc() => (_now?.call() ?? DateTime.now()).toUtc();

  DateTime nowLocal() => nowUtc().toLocal();

  /// A clock that runs [offset] ahead of this one (behind when negative), for walking a day
  /// boundary or a reminder without waiting. Build one `now` from it and pass it to every clock seam.
  TaskClock offsetBy(Duration offset) => TaskClock(() => nowUtc().add(offset));
}
