/// URL building for [ApiClient].
library;

/// [path] under [base] (keeping the base path prefix), with [query] added.
/// Null query values are dropped; an iterable repeats the key. A query string
/// inside [path] is kept.
Uri buildApiUri(Uri base, String path, [Map<String, Object?>? query]) {
  final root = base.path.endsWith('/') ? base.path.substring(0, base.path.length - 1) : base.path;
  final rel = Uri.parse(path.startsWith('/') ? path : '/$path');
  final params = <String, List<String>>{...rel.queryParametersAll};
  for (final e in (query ?? const <String, Object?>{}).entries) {
    final v = e.value;
    if (v == null) continue;
    params[e.key] = v is Iterable ? [for (final x in v) '$x'] : ['$v'];
  }
  return base.replace(path: '$root${rel.path}', queryParameters: params.isEmpty ? null : params);
}
