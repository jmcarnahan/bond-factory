/// Task priority and its wire integer.
library;

enum TaskPriority {
  low(1),
  normal(2),
  high(3);

  const TaskPriority(this.wire);
  final int wire;

  /// Null or an unknown value gives null (not set).
  static TaskPriority? fromWire(int? v) {
    for (final p in values) {
      if (p.wire == v) return p;
    }
    return null;
  }
}
