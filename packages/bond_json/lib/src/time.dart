/// Timestamp reading and writing. Everything is UTC.
library;

import 'json.dart';

final RegExp _hasZone = RegExp(r'(Z|[+-]\d{2}(:?\d{2})?)$', caseSensitive: false);

// A date-only value ("2026-11-08") has dashes that look like an offset.
final RegExp _dateOnly = RegExp(r'^\d{4}-\d{2}-\d{2}$');

/// A UTC instant from the ISO-8601 string at [k].
///
/// `Z`, numeric offsets and naive strings (no zone, treated as UTC) are all
/// accepted and all come back as UTC. Null when missing, `null` or empty.
/// Integers (epoch seconds or millis) are not accepted and throw
/// [JsonShapeError], as does a string that is not a timestamp.
DateTime? jtime(Map<Object?, Object?> m, String k) {
  final v = m[k];
  if (v == null) return null;
  if (v is! String) throw JsonShapeError(k, 'ISO-8601 String', describeJsonType(v));
  final s = v.trim();
  if (s.isEmpty) return null;
  final String text;
  if (_dateOnly.hasMatch(s)) {
    text = '${s}T00:00:00Z';
  } else {
    text = _hasZone.hasMatch(s) ? s : '${s}Z';
  }
  final parsed = DateTime.tryParse(text);
  if (parsed == null) throw JsonShapeError(k, 'ISO-8601 timestamp', "'$v'");
  return parsed.toUtc();
}

/// [t] as UTC ISO-8601 with millisecond precision and a trailing `Z`
/// (`2026-11-08T10:30:00.000Z`).
String jiso(DateTime t) =>
    DateTime.fromMillisecondsSinceEpoch(t.millisecondsSinceEpoch, isUtc: true).toIso8601String();
