/// The single HTTP entry point: bearer token, timeouts, typed failures and the
/// one-shot session renewal on a 401.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as h;

import 'error_body.dart';
import 'exceptions.dart';
import 'multipart.dart';
import 'token_source.dart';
import 'uri_builder.dart';

part 'client_session.dart';

const Duration kHeaderTimeout = Duration(seconds: 20);
const Duration kApiTimeout = Duration(seconds: 60);
const Duration kUploadTimeout = Duration(seconds: 120);

/// Adds the bearer token, decodes JSON and turns failures into [ApiException]s.
///
/// The JSON verbs are an extension in `client_requests.dart` and `sse` is one in
/// `sse.dart`; both go through [request] and [openStream].
/// A 401 to an authenticated request asks [onUnauthorized] to renew the session
/// once (concurrent 401s share the call) and replays the request exactly once
/// on `renewed`. When the session is over [onSessionRevoked] (code
/// `session_revoked`) and [onSessionExpired] run once. A 403 `deactivated` runs
/// [onDeactivated] once. The full rules are in the README.
class ApiClient {
  ApiClient({
    required this.baseUrl,
    required h.Client http,
    this.tokens,
    this.onUnauthorized,
    this.onSessionRevoked,
    this.onSessionExpired,
    this.onDeactivated,
    this.headerTimeout = kHeaderTimeout,
    this.timeout = kApiTimeout,
    this.uploadTimeout = kUploadTimeout,
    this.isWeb = false,
    this.log,
    this.streamClientFactory,
    this.endsSession,
  }) : _http = http;

  /// The API root, including any prefix (`https://host/api/v1`).
  final Uri baseUrl;
  final TokenSource? tokens;
  final h.Client _http;

  /// How long to wait for the response headers.
  final Duration headerTimeout;

  /// The overall limit for one call: headers and the whole body.
  final Duration timeout;

  /// The overall limit for a multipart upload.
  final Duration uploadTimeout;
  /// True in a browser build: a no-answer failure may be a CORS block.
  final bool isWeb;

  /// Where one-line diagnostics go (never tokens or bodies).
  final void Function(String)? log;

  /// Gives each `sse` call its own client so cancelling closes the connection.
  /// Without it SSE uses the shared client.
  final h.Client Function()? streamClientFactory;

  /// Decides whether a 401 ends the session. Null means every 401 does. It is
  /// asked on every 401 of a signed-in call (not an auth path), before and after
  /// a renewal. When it returns false (say a business 401 such as "mail account
  /// not connected"), nothing is renewed and no session hook runs: the call
  /// throws [Unauthorized] with the code kept. A throwing callback is logged
  /// and counts as true.
  final bool Function(ErrorBody)? endsSession;

  /// Renews the session after a 401 (see the class comment). Settable because
  /// the object that renews often needs this client first.
  Future<SessionRefresh> Function()? onUnauthorized;

  /// Runs when the session is over and the server said `session_revoked`.
  Future<void> Function()? onSessionRevoked;

  /// Runs when the session is over (the person has to sign in again).
  Future<void> Function()? onSessionExpired;

  /// Runs when an authenticated request is refused with 403 `deactivated`.
  Future<void> Function()? onDeactivated;

  Future<SessionRefresh>? _refreshing;
  bool _endedFired = false;
  bool _deactivatedFired = false;

  static bool _isAuthPath(String path) => authPathsExcludedFromRenewal.any(path.endsWith);

  /// [path] under [baseUrl], with [query] added (null values dropped, lists
  /// repeat the key).
  Uri uri(String path, [Map<String, Object?>? query]) => buildApiUri(baseUrl, path, query);

  Map<String, String> _headers({bool json = true, String accept = 'application/json'}) {
    final token = tokens?.token;
    return {
      if (json) 'Content-Type': 'application/json',
      'Accept': accept,
      if (token != null) 'Authorization': 'Bearer $token',
    };
  }

  void _log(String line) {
    try { log?.call(line); } catch (_) {}
  }
  /// One JSON call. The decoded body, or null for an empty one.
  ///
  /// [timeout] replaces the client's overall limit (headers plus the whole body)
  /// for this call. [headerTimeout] replaces the wait for the response headers;
  /// the header wait is never longer than the overall limit.
  Future<Object?> request(String method, String path,
      {Object? body, Map<String, Object?>? query, Duration? timeout, Duration? headerTimeout}) {
    final url = uri(path, query);
    return _decode(() {
      final r = h.Request(method, url)..headers.addAll(_headers());
      if (body != null) r.body = jsonEncode(body);
      return r;
    }, headerLimit: headerTimeout ?? this.headerTimeout, limit: timeout ?? this.timeout, path: path);
  }

  /// A multipart POST of text [fields] and in-memory [files]. Returns the
  /// decoded JSON answer.
  Future<Object?> postMultipart(
    String path, {
    Map<String, String> fields = const {},
    List<ApiFile> files = const [],
  }) {
    final url = uri(path);
    return _decode(
      () => buildMultipart('POST', url, fields, files)..headers.addAll(_headers(json: false)),
      headerLimit: uploadTimeout,
      limit: uploadTimeout,
      path: path,
    );
  }

  /// A GET whose body is returned as is (a photo, a PDF).
  Future<Uint8List> getBytes(String path,
          {Map<String, Object?>? query, Duration? timeout, Duration? headerTimeout}) =>
      requestBytes('GET', path, query: query, timeout: timeout, headerTimeout: headerTimeout);

  /// Like [request] (same token, renewal and errors) but the answer body is
  /// returned as bytes: POST JSON, receive a PDF. [accept] is the Accept header.
  Future<Uint8List> requestBytes(
    String method,
    String path, {
    Object? body,
    Map<String, Object?>? query,
    String accept = '*/*',
    Duration? timeout,
    Duration? headerTimeout,
  }) async {
    final url = uri(path, query);
    final limit = timeout ?? this.timeout;
    final clock = Stopwatch()..start();
    final streamed = await _open(() {
      final r = h.Request(method, url)..headers.addAll(_headers(json: body != null, accept: accept));
      if (body != null) r.body = jsonEncode(body);
      return r;
    }, clock: clock, headerLimit: headerTimeout ?? this.headerTimeout, limit: limit);
    return _readBytes(streamed, clock, limit);
  }

  /// Sends a request and returns once the response headers say 2xx; every
  /// other outcome is thrown as an [ApiException]. Used by `sse`.
  Future<h.StreamedResponse> openStream(
    String method,
    String path, {
    Object? body,
    Map<String, Object?>? query,
    h.Client? client,
    Duration? timeout,
    Duration? headerTimeout,
  }) {
    final url = uri(path, query);
    return _open(() {
      final r = h.Request(method, url)..headers.addAll(_headers(json: body != null, accept: 'text/event-stream'));
      if (body != null) r.body = jsonEncode(body);
      return r;
    }, clock: Stopwatch()..start(),
        headerLimit: headerTimeout ?? this.headerTimeout, limit: timeout ?? this.timeout, client: client);
  }

  void close() => _http.close();

  Future<Object?> _decode(
    h.BaseRequest Function() make, {
    required Duration headerLimit,
    required Duration limit,
    required String path,
  }) async {
    final clock = Stopwatch()..start();
    final streamed = await _open(make, clock: clock, headerLimit: headerLimit, limit: limit);
    final bytes = await _readBytes(streamed, clock, limit);
    if (bytes.isEmpty) return null;
    try {
      return jsonDecode(utf8.decode(bytes));
    } on FormatException catch (e) {
      // Typically an HTML page from a proxy or the wrong server.
      throw BadResponse(path, 'non-JSON response: ${e.message}');
    }
  }

  NetworkFailure _failure(NetworkFailureKind kind, String message, [Object? cause, int? status]) =>
      NetworkFailure(kind, baseUrl: baseUrl.toString(), status: status, message: message, cause: cause?.toString());

  Future<Uint8List> _readBytes(h.StreamedResponse streamed, Stopwatch clock, Duration limit) async {
    final left = limit - clock.elapsed;
    final cap = left > Duration.zero ? left : const Duration(milliseconds: 1);
    try {
      return await streamed.stream.toBytes().timeout(cap);
    } on TimeoutException catch (e) {
      throw _failure(NetworkFailureKind.timeout, 'Request timed out', e);
    } catch (e) {
      throw _failure(NetworkFailureKind.noAnswer, 'Connection lost while reading the answer', e);
    }
  }

  Future<h.StreamedResponse> _open(
    h.BaseRequest Function() make, {
    required Stopwatch clock,
    required Duration headerLimit,
    required Duration limit,
    h.Client? client,
  }) async {
    var retried = false;
    var rejected = false;
    var sends = 0; // hard stop: at most the original and one replay
    while (true) {
      clock.reset(); // a replay after a renewal gets the full header and total budgets again
      if (++sends > 2) throw _failure(NetworkFailureKind.http, 'Too many renewal retries');
      final sentWith = tokens?.token;
      final h.BaseRequest request;
      try {
        request = make();
      } catch (e) {
        throw _failure(NetworkFailureKind.badBody, 'Could not build the request', e);
      }
      final h.StreamedResponse streamed;
      try {
        final left = limit - clock.elapsed;
        final wait = headerLimit < left ? headerLimit : left;
        streamed = await (client ?? _http)
            .send(request)
            .timeout(wait > Duration.zero ? wait : const Duration(milliseconds: 1));
      } on TimeoutException catch (e) {
        _log('${request.method} ${request.url.path}: timed out');
        throw _failure(NetworkFailureKind.timeout, 'Request timed out', e);
      } catch (e) {
        _log('${request.method} ${request.url.path}: no answer');
        final why = isWeb ? ' (or the browser blocked it)' : '';
        throw _failure(NetworkFailureKind.noAnswer, 'No answer from the server$why', e);
      }
      final status = streamed.statusCode;
      if (status >= 200 && status < 300) {
        _endedFired = false;
        _deactivatedFired = false;
        return streamed;
      }
      final text = utf8.decode(await _readBytes(streamed, clock, limit), allowMalformed: true);
      final path = request.url.path;
      if (status == 401 && sentWith != null && !_isAuthPath(path)) {
        // Asked on every 401 of the call, before and after a renewal.
        if (endsSession != null) {
          final body = _readBody(status, text);
          if (!_endsSessionSafe(body)) throw body.toException();
        }
      }
      if (status == 401 && sentWith != null && !_isAuthPath(path) && !retried && onUnauthorized != null) {
        retried = true;
        // Another request may have renewed the session while this one was in flight.
        final now = tokens?.token;
        if (now != null && now != sentWith) continue;
        _log('401 on $path: renewing the session');
        switch (await _renewOnce()) {
          case SessionRefresh.renewed:
            continue;
          case SessionRefresh.offline:
            throw _failure(NetworkFailureKind.noAnswer, 'Could not renew the session');
          case SessionRefresh.rejected:
            rejected = true;
        }
      }
      throw await _fail(status, text, path, signedIn: sentWith != null, rejected: rejected);
    }
  }
}
