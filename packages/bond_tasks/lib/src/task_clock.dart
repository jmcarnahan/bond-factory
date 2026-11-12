/// An injectable "now", so tests and the ticker control time.
library;

class TaskClock {
  const TaskClock([DateTime Function()? now]) : _now = now;

  final DateTime Function()? _now;

  DateTime nowUtc() => (_now?.call() ?? DateTime.now()).toUtc();

  DateTime nowLocal() => nowUtc().toLocal();
}
