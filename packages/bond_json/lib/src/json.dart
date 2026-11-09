/// Null-safe readers for decoded JSON maps.
///
/// A missing key or an explicit `null` reads as `null` (or an empty list); a
/// value of the wrong type throws [JsonShapeError]. Nothing here throws for a
/// key the server merely left out, so an old client survives a new field.
library;

/// A JSON value had the wrong type.
///
/// [path] names the key (or `key[index].inner` for list elements), [expected]
/// the wanted type and [actual] the runtime type that was found.
class JsonShapeError implements Exception {
  const JsonShapeError(this.path, this.expected, this.actual);

  final String path;
  final String expected;
  final String actual;

  @override
  String toString() => 'JsonShapeError: expected $expected at '
      "'${path.isEmpty ? '<root>' : path}' but found $actual";
}

/// The `Type` name of [v] as printed in a [JsonShapeError].
String describeJsonType(Object? v) => v == null ? 'null' : v.runtimeType.toString();

/// A string at [k], or null when missing or `null`.
String? jstr(Map<Object?, Object?> m, String k) {
  final v = m[k];
  if (v == null) return null;
  if (v is String) return v;
  throw JsonShapeError(k, 'String', describeJsonType(v));
}

/// An int at [k]: accepts an int, any num (truncated toward zero) or a numeric
/// string. Null when missing or `null`.
int? jint(Map<Object?, Object?> m, String k) {
  final v = m[k];
  if (v == null) return null;
  if (v is int) return v;
  if (v is num) {
    if (v.isFinite) return v.truncate();
    throw JsonShapeError(k, 'int', v.toString());
  }
  if (v is String) {
    final parsed = int.tryParse(v.trim()) ?? double.tryParse(v.trim())?.truncate();
    if (parsed != null) return parsed;
  }
  throw JsonShapeError(k, 'int', describeJsonType(v));
}

/// A double at [k]: accepts any num or a numeric string.
double? jnum(Map<Object?, Object?> m, String k) {
  final v = m[k];
  if (v == null) return null;
  if (v is num) return v.toDouble();
  if (v is String) {
    final parsed = double.tryParse(v.trim());
    if (parsed != null) return parsed;
  }
  throw JsonShapeError(k, 'num', describeJsonType(v));
}

/// A bool at [k]. Strings and numbers are not coerced.
bool? jbool(Map<Object?, Object?> m, String k) {
  final v = m[k];
  if (v == null) return null;
  if (v is bool) return v;
  throw JsonShapeError(k, 'bool', describeJsonType(v));
}

/// A string-keyed copy of the map at [k].
Map<String, Object?>? jmap(Map<Object?, Object?> m, String k) {
  final v = m[k];
  if (v == null) return null;
  if (v is Map) return _stringKeyed(v);
  throw JsonShapeError(k, 'Map', describeJsonType(v));
}

Map<String, Object?> _stringKeyed(Map<Object?, Object?> v) => {
      for (final e in v.entries) e.key.toString(): e.value,
    };

/// The list at [k], each element read by [f]. Missing or `null` gives `const []`.
/// A [JsonShapeError] thrown by [f] gets its path prefixed with `k[index]`.
List<T> jlist<T>(Map<Object?, Object?> m, String k, T Function(Object?) f) {
  final v = m[k];
  if (v == null) return const [];
  if (v is! List) throw JsonShapeError(k, 'List', describeJsonType(v));
  return _mapList(v, f, k);
}

/// Like [jlist] for a top-level value, such as a response body that is an array.
List<T> jlistOf<T>(Object? v, T Function(Object?) f) {
  if (v == null) return const [];
  if (v is! List) throw JsonShapeError('', 'List', describeJsonType(v));
  return _mapList(v, f, '');
}

List<T> _mapList<T>(List<Object?> v, T Function(Object?) f, String path) {
  final out = <T>[];
  for (var i = 0; i < v.length; i++) {
    try {
      out.add(f(v[i]));
    } on JsonShapeError catch (e) {
      final inner = e.path.isEmpty ? '' : '.${e.path}';
      throw JsonShapeError('$path[$i]$inner', e.expected, e.actual);
    }
  }
  return out;
}
