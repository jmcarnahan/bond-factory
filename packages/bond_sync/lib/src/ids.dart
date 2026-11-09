/// Ids and stamps for local writes.
library;

import 'dart:convert';
import 'dart:math';

final Random _rng = Random.secure();

/// A fresh random (version 4) UUID, lower-case and hyphenated. The primary key
/// of every row the device creates, so a retry is the same row.
String newId() {
  final b = List<int>.generate(16, (_) => _rng.nextInt(256));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  String h(int from, int to) =>
      b.sublist(from, to).map((x) => x.toRadixString(16).padLeft(2, '0')).join();
  return '${h(0, 4)}-${h(4, 6)}-${h(6, 8)}-${h(8, 10)}-${h(10, 16)}';
}

/// A time as the stamp local writes store: UTC ISO 8601.
String isoOf(DateTime t) => t.toUtc().toIso8601String();

/// The `_metadata` a write carries so the uploader knows what it was
/// (`{"action": ...}`).
String actionOf(String action) => jsonEncode({'action': action});
