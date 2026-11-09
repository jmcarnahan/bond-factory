/// The random id a client sends with every refresh-token rotation, so the
/// server can tell a retry of a lost answer from a replay by a thief.
library;

import 'dart:math';

/// Hands out one rotation id at a time. The same id is returned until
/// [succeeded] is called, so a retry of an unanswered rotation reuses it; the
/// next rotation after a success gets a fresh one.
class RotationIds {
  RotationIds({Random? random}) : _random = random ?? Random.secure();

  final Random _random;
  String? _current;

  /// The id for the rotation being attempted: 16 random bytes as 32 hex chars.
  String get current => _current ??= _make();

  /// Takes over an id persisted by an earlier run, so its retry reuses it.
  void adopt(String id) => _current = id;

  /// The rotation was answered and stored: the next one needs a new id.
  void succeeded() => _current = null;

  String _make() {
    final b = StringBuffer();
    for (var i = 0; i < 16; i++) {
      b.write(_random.nextInt(256).toRadixString(16).padLeft(2, '0'));
    }
    return b.toString();
  }
}
