/// Parsing helpers shared by the model, totals and measurement parsers. Not exported.
library;

/// Throws a [FormatException] whose message starts with the JSON [path] of the problem.
Never badJson(String path, String msg) => throw FormatException('$path: $msg');

Map<String, dynamic> asMap(Object? v, String path) {
  if (v is Map<String, dynamic>) return v;
  if (v is Map) return v.map((k, x) => MapEntry('$k', x));
  badJson(path, 'expected an object');
}

List<Object?> asList(Object? v, String path) {
  if (v is List) return v;
  badJson(path, 'expected an array');
}

double asNum(Object? v, String path) {
  if (v is num && v.isFinite) return v.toDouble();
  badJson(path, 'expected a finite number');
}

double numOr(Map<String, dynamic> m, String key, String path, double fallback) =>
    m[key] == null ? fallback : asNum(m[key], '$path.$key');

double? numOrNull(Map<String, dynamic> m, String key, String path) =>
    m[key] == null ? null : asNum(m[key], '$path.$key');

String asStr(Object? v, String path) {
  if (v is String) return v;
  badJson(path, 'expected a string');
}

String strOr(Map<String, dynamic> m, String key, String path, String fallback) =>
    m[key] == null ? fallback : asStr(m[key], '$path.$key');

List<String> strList(Object? v, String path) =>
    v == null ? const [] : [for (final (i, x) in asList(v, path).indexed) asStr(x, '$path[$i]')];

/// A point in feet (model space: x east, y north) or in pixels (scene space: y down).
typedef Pt = ({double x, double y});

Pt asPt(Object? v, String path) {
  if (v is List && v.length == 2) {
    return (x: asNum(v[0], '$path[0]'), y: asNum(v[1], '$path[1]'));
  }
  badJson(path, 'expected [x, y]');
}

List<Pt> asPoly(Object? v, String path) {
  final l = asList(v, path);
  if (l.length < 3) badJson(path, 'a polygon needs at least 3 points');
  return [for (var i = 0; i < l.length; i++) asPt(l[i], '$path[$i]')];
}

List<Object?> ptJson(Pt p) => [p.x, p.y];
List<Object?> polyJson(List<Pt> p) => [for (final q in p) ptJson(q)];

/// The value of [values] whose [name] is [s], or null.
T? enumOrNull<T>(String s, List<T> values, String Function(T) name) {
  for (final v in values) {
    if (name(v) == s) return v;
  }
  return null;
}
