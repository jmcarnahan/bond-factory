import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'tokens.dart';

enum MeasureMethod {
  auto('auto', 'Auto'),
  lidar('lidar_skeleton', 'LiDAR'),
  lidarAgent('lidar_agent', 'LiDAR + agent'),
  solarAgent('solar_agent', 'Solar + agent');

  const MeasureMethod(this.wire, this.label);
  final String wire;
  final String label;
}

/// A job the service reported as failed, or an HTTP error answer: `code: message`.
class ServiceFailure implements Exception {
  const ServiceFailure(this.code, this.message, {this.retryable = false});

  final String code, message;
  final bool retryable;

  @override
  String toString() => '$code: $message';
}

/// One poll of `GET /v1/measurements/{id}`.
class JobSnapshot {
  const JobSnapshot({required this.id, required this.status, this.error, this.result});

  factory JobSnapshot.fromJson(Map<String, dynamic> j) => JobSnapshot(
        id: '${j['id']}',
        status: '${j['status']}',
        error: j['error'] is Map ? ServiceClient.failureOf(j['error'] as Map) : null,
        result: j['result'] is Map ? (j['result'] as Map).cast<String, dynamic>() : null,
      );

  final String id;

  /// `queued`, `running`, `done` or `failed`.
  final String status;
  final ServiceFailure? error;

  /// The 0.2 envelope once `status` is `done`.
  final Map<String, dynamic>? result;

  bool get finished => status == 'done' || status == 'failed';
}

/// Client for the roof measure service (contract C1): submit a job, then poll it.
///
/// The bearer token comes from `--dart-define=ROOF_TOKEN=...` and is for local development only;
/// a real app keeps it on its own backend. The base URL comes from `--dart-define=ROOF_SERVICE=...`.
class ServiceClient {
  ServiceClient({
    String? baseUrl,
    String? token,
    http.Client? client,
    this.pollInterval = DemoTokens.pollInterval,
    this.jobTimeout = DemoTokens.jobTimeout,
    this.pollRetries = 3,
  })  : base = baseUrl ?? const String.fromEnvironment('ROOF_SERVICE', defaultValue: DemoTokens.serviceDefault),
        token = token ?? const String.fromEnvironment('ROOF_TOKEN'),
        _http = client ?? http.Client();

  final String base, token;
  final Duration pollInterval, jobTimeout;

  /// Retries of a single failed poll before the job is given up on.
  final int pollRetries;
  final http.Client _http;

  Map<String, String> get _headers => {
        if (token.isNotEmpty) 'authorization': 'Bearer $token',
        'content-type': 'application/json',
      };

  /// Submits a job and returns its id (`202 {id, status}`).
  Future<String> submit(String address, MeasureMethod method, {bool verify = true}) async {
    final res = await _http
        .post(
          Uri.parse('$base/v1/measurements'),
          headers: _headers,
          body: jsonEncode({'address': address, 'method': method.wire, 'verify': verify}),
        )
        .timeout(DemoTokens.requestTimeout);
    final body = _decode(res);
    if (res.statusCode != 202 && res.statusCode != 200) throw _httpFailure(res, body);
    final id = body['id'];
    if (id is! String || id.isEmpty) {
      throw const ServiceFailure('invalid_response', 'The service accepted the job but sent no id.');
    }
    return id;
  }

  /// [poll] with up to [pollRetries] retries for transient trouble: a timeout, a network error,
  /// 429 or a 5xx answer. Other failures (401, 404 unknown_job) surface at once.
  Future<JobSnapshot> _pollRetrying(String id) async {
    for (var attempt = 0;; attempt++) {
      try {
        return await poll(id);
      } catch (e) {
        final transient = e is! ServiceFailure ||
            e.retryable ||
            e.code == 'http_429' ||
            RegExp(r'^http_5\d\d$').hasMatch(e.code);
        if (!transient || attempt >= pollRetries) rethrow;
        await Future<void>.delayed(pollInterval);
      }
    }
  }

  /// One poll of a job.
  Future<JobSnapshot> poll(String id) async {
    final res = await _http
        .get(Uri.parse('$base/v1/measurements/$id'), headers: _headers)
        .timeout(DemoTokens.requestTimeout);
    final body = _decode(res);
    if (res.statusCode != 200) throw _httpFailure(res, body);
    return JobSnapshot.fromJson(body);
  }

  /// Submits, then polls every [pollInterval] until the job is `done` or `failed`. [onStatus] gets
  /// a short text for inline display each time. Returns the envelope; a failed job throws a
  /// [ServiceFailure] (`error.code: error.message`).
  Future<Map<String, dynamic>> measure(
    String address,
    MeasureMethod method, {
    bool verify = true,
    void Function(String status)? onStatus,
  }) async {
    onStatus?.call('Submitting...');
    final id = await submit(address, method, verify: verify);
    final clock = Stopwatch()..start();
    while (true) {
      final snap = await _pollRetrying(id);
      onStatus?.call('Job ${snap.status} (${clock.elapsed.inSeconds} s)');
      if (snap.status == 'done') {
        final result = snap.result;
        if (result == null) throw const ServiceFailure('measurement_failed', 'The job finished without a result.');
        return result;
      }
      if (snap.status == 'failed') {
        throw snap.error ?? const ServiceFailure('measurement_failed', 'The job failed.');
      }
      if (clock.elapsed > jobTimeout) {
        throw ServiceFailure('timeout', 'No result after ${jobTimeout.inSeconds} s.', retryable: true);
      }
      await Future<void>.delayed(pollInterval);
    }
  }

  /// Fixture stems (no `.json`) the service offers (debug builds only), or empty when it is not
  /// reachable, refuses, or answers with an unexpected shape. The service returns a list of
  /// `{name, file, bytes}` objects; a plain list of strings is tolerated.
  Future<List<String>> fixtures() async {
    try {
      final res = await _http.get(Uri.parse('$base/fixtures'), headers: _headers).timeout(DemoTokens.listTimeout);
      if (res.statusCode != 200) return const [];
      return parseFixtureNames(jsonDecode(res.body));
    } catch (_) {
      return const [];
    }
  }

  /// Normalises a decoded /fixtures body to a list of stems. Returns const []
  /// on any shape it does not understand.
  static List<String> parseFixtureNames(Object? body) {
    if (body is! List) return const [];
    final out = <String>[];
    for (final e in body) {
      final Object? raw = e is Map ? e['name'] : e;
      if (raw is! String || raw.isEmpty) return const [];
      out.add(fixtureStem(raw));
    }
    return out;
  }

  static String fixtureStem(String name) =>
      name.endsWith('.json') ? name.substring(0, name.length - '.json'.length) : name;

  Future<Map<String, dynamic>> fixtureJson(String name) async {
    final res = await _http
        .get(Uri.parse('$base/fixtures/${fixtureStem(name)}'), headers: _headers)
        .timeout(DemoTokens.listTimeout);
    if (res.statusCode != 200) throw ServiceFailure('http_${res.statusCode}', 'Service answered ${res.statusCode}');
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  /// `{code, message, retryable}` as the service sends it.
  static ServiceFailure failureOf(Map e) => ServiceFailure(
        '${e['code'] ?? 'measurement_failed'}',
        '${e['message'] ?? ''}',
        retryable: e['retryable'] == true,
      );

  static Map<String, dynamic> _decode(http.Response res) {
    try {
      final j = jsonDecode(res.body);
      if (j is Map) return j.cast<String, dynamic>();
    } catch (_) {}
    return {'raw': _short(res.body)};
  }

  static ServiceFailure _httpFailure(http.Response res, Map<String, dynamic> body) {
    final e = body['error'];
    if (e is Map) return failureOf(e);
    return ServiceFailure('http_${res.statusCode}', 'Service answered ${res.statusCode}: ${_short(res.body)}');
  }

  static String _short(String s) => s.length > 300 ? '${s.substring(0, 300)}...' : s;
}
