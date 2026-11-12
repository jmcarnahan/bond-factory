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
  final parsed = _parse(text);
  if (parsed == null) throw JsonShapeError(k, 'ISO-8601 timestamp', "'$v'");
  return parsed;
}

/// Like [jtime], but never throws: null when missing, `null`, empty, not a
/// String, or not a real timestamp (including an impossible calendar date).
/// Use it for a field where a bad value should read as "unknown" instead of
/// breaking the whole payload.
DateTime? jtimeOrNull(Map<Object?, Object?> m, String k) {
  final v = m[k];
  if (v is! String) return null;
  final s = v.trim();
  if (s.isEmpty) return null;
  final String text;
  if (_dateOnly.hasMatch(s)) {
    text = '${s}T00:00:00Z';
  } else {
    text = _hasZone.hasMatch(s) ? s : '${s}Z';
  }
  return _parse(text);
}

// Both the date-only and the full form go through here. Dart rolls an
// impossible field over (2026-02-30 becomes March 2, 24:00 becomes the next
// day, 23:59:60 the next minute), so the written fields are checked first and
// a bad one is rejected. The check covers the extended form (`2026-11-08`),
// the basic form (`20261108T101010Z`) and an hour-only time (`2026-11-08T10`).
// It reads a four-digit year at the start of the string; an extended year
// (`-2026-...`, `10000-...`) is not checked and keeps Dart's rolling.
final RegExp _fields = RegExp(r'^(\d{4})-?(\d{2})-?(\d{2})(?:[Tt ](\d{2})(?::?(\d{2})(?::?(\d{2}))?)?)?');

DateTime? _parse(String text) {
  final f = _fields.firstMatch(text);
  if (f != null) {
    final y = int.parse(f.group(1)!);
    final mo = int.parse(f.group(2)!);
    final d = int.parse(f.group(3)!);
    if (mo < 1 || mo > 12) return null;
    if (d < 1 || d > DateTime.utc(y, mo + 1, 0).day) return null;
    final h = f.group(4);
    if (h != null) {
      if (int.parse(h) > 23) return null;
      final min = f.group(5);
      if (min != null && int.parse(min) > 59) return null;
      final sec = f.group(6);
      if (sec != null && int.parse(sec) > 59) return null;
    }
  }
  return DateTime.tryParse(text)?.toUtc();
}

/// [t] as UTC ISO-8601 with millisecond precision and a trailing `Z`
/// (`2026-11-08T10:30:00.000Z`).
String jiso(DateTime t) =>
    DateTime.fromMillisecondsSinceEpoch(t.millisecondsSinceEpoch, isUtc: true).toIso8601String();
