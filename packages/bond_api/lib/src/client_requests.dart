/// The JSON verbs of [ApiClient].
library;

import 'client.dart';
import 'exceptions.dart';

/// `Map<String, Object?>` in and out. An empty answer body reads as `{}`; an
/// answer of another shape throws [BadResponse].
extension ApiClientJson on ApiClient {
  Future<Map<String, Object?>> getJson(String path, {Map<String, Object?>? query}) async =>
      _asMap(await request('GET', path, query: query), path);

  Future<Map<String, Object?>> postJson(String path, {Object? body, Map<String, Object?>? query}) async =>
      _asMap(await request('POST', path, body: body, query: query), path);

  Future<Map<String, Object?>> putJson(String path, {Object? body, Map<String, Object?>? query}) async =>
      _asMap(await request('PUT', path, body: body, query: query), path);

  Future<Map<String, Object?>> patchJson(String path, {Object? body, Map<String, Object?>? query}) async =>
      _asMap(await request('PATCH', path, body: body, query: query), path);

  Future<Map<String, Object?>> deleteJson(String path, {Map<String, Object?>? query}) async =>
      _asMap(await request('DELETE', path, query: query), path);

  /// A GET whose answer is a JSON array.
  Future<List<Object?>> getJsonList(String path, {Map<String, Object?>? query}) async {
    final v = await request('GET', path, query: query);
    if (v == null) return const [];
    if (v is List) return v;
    throw BadResponse(path, 'expected a list, got ${v.runtimeType}');
  }
}

Map<String, Object?> _asMap(Object? v, String path) {
  if (v == null) return const {};
  if (v is Map) return {for (final e in v.entries) e.key.toString(): e.value};
  throw BadResponse(path, 'expected an object, got ${v.runtimeType}');
}
