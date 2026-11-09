/// Enum reading from wire strings.
library;

/// The member of [values] whose [wireOf] equals [wire]; null for a null or
/// unknown string, so a value added by a newer server never throws.
T? enumByWire<T extends Enum>(Iterable<T> values, String? wire, String Function(T) wireOf) {
  if (wire == null) return null;
  for (final v in values) {
    if (wireOf(v) == wire) return v;
  }
  return null;
}
