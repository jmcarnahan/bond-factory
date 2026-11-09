/// An in-memory `http.Client` that serves queued answers and records requests.
library;

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

/// One answer [CannedHttpClient] can serve.
class CannedResponse {
  const CannedResponse(this.status, {this.body = '', this.headers = const {}, this.error});

  /// A JSON answer (status 200 unless given).
  factory CannedResponse.json(Object? json, {int status = 200, Map<String, String> headers = const {}}) =>
      CannedResponse(
        status,
        body: jsonEncode(json),
        headers: {'content-type': 'application/json', ...headers},
      );

  /// Throw [error] from `send` instead of answering (a dead connection).
  const CannedResponse.fail(Object this.error)
      : status = 0,
        body = '',
        headers = const {};

  final int status;
  final String body;
  final Map<String, String> headers;
  final Object? error;
}

/// A request as the client received it.
class RecordedRequest {
  const RecordedRequest(this.method, this.url, this.headers, this.bodyBytes);

  final String method;
  final Uri url;
  final Map<String, String> headers;
  final List<int> bodyBytes;

  String get path => url.path;

  String get body => utf8.decode(bodyBytes, allowMalformed: true);

  /// The body decoded as JSON.
  Object? get json => jsonDecode(body);

  @override
  String toString() => '$method $path';
}

/// Queues of answers keyed by method and path.
///
/// Answers for one key are served in order; the last one repeats for every
/// further request, so a single `json(...)` answers all calls.
class CannedResponses {
  final Map<String, List<CannedResponse>> _byKey = {};

  static String _key(String method, String path) => '${method.toUpperCase()} $path';

  /// Queue [response] for [method] [path] (the path without host or query).
  void on(String method, String path, CannedResponse response) =>
      _byKey.putIfAbsent(_key(method, path), () => []).add(response);

  /// Queue a JSON answer.
  void json(String method, String path, Object? body, {int status = 200}) =>
      on(method, path, CannedResponse.json(body, status: status));

  /// Queue an answer that throws, as a dead connection does.
  void fail(String method, String path, Object error) => on(method, path, CannedResponse.fail(error));

  /// The next answer for the key, or null when none was queued.
  CannedResponse? next(String method, String path) {
    final queue = _byKey[_key(method, path)];
    if (queue == null || queue.isEmpty) return null;
    return queue.length > 1 ? queue.removeAt(0) : queue.first;
  }
}

/// Serves [responses] by method and path and records every request in
/// [requests]. A request with no canned answer gets a 404 with a JSON detail
/// saying so, and is also listed in [unmatched].
class CannedHttpClient extends http.BaseClient {
  CannedHttpClient([CannedResponses? responses]) : responses = responses ?? CannedResponses();

  final CannedResponses responses;
  final List<RecordedRequest> requests = [];
  final List<RecordedRequest> unmatched = [];
  bool closed = false;

  /// Requests with this [method] (any case) and [path].
  List<RecordedRequest> requestsTo(String method, String path) => [
        for (final r in requests)
          if (r.method == method.toUpperCase() && r.path == path) r,
      ];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final bytes = await request.finalize().toBytes();
    final recorded = RecordedRequest(request.method, request.url, Map.of(request.headers), bytes);
    requests.add(recorded);
    final canned = responses.next(request.method, request.url.path);
    if (canned == null) {
      unmatched.add(recorded);
      return _answer(
        CannedResponse.json({'detail': 'no canned response for $recorded'}, status: 404),
        request,
      );
    }
    final error = canned.error;
    if (error != null) throw error;
    return _answer(canned, request);
  }

  http.StreamedResponse _answer(CannedResponse r, http.BaseRequest request) => http.StreamedResponse(
        Stream.value(utf8.encode(r.body)),
        r.status,
        headers: r.headers,
        request: request,
      );

  @override
  void close() => closed = true;
}
