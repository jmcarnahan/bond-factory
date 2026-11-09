import 'dart:convert';

import 'package:bond_api/bond_api.dart';
import 'package:bond_auth/bond_auth.dart';
import 'package:http/http.dart' as h;
import 'package:http/testing.dart';

/// One request the fake server saw.
class Seen {
  Seen(this.method, this.path, this.body);
  final String method;
  final String path;
  final Map<String, Object?> body;
}

/// An [ApiClient] over a MockClient that records requests and answers canned
/// JSON by `METHOD path`; a value may be a function of the request body.
class FakeServer {
  FakeServer([Map<String, Object> answers = const {}]) : answers = {...answers};

  final Map<String, Object> answers;
  final List<Seen> seen = [];

  /// Status for a path answered with an error: `{'POST /x': (401, {'code': ...})}`.
  final Map<String, (int, Map<String, Object?>)> errors = {};

  late final ApiClient api = ApiClient(
    baseUrl: Uri.parse('https://api.test'),
    http: MockClient((h.Request r) async {
      final raw = r.body.isEmpty ? null : jsonDecode(r.body);
      final body = raw is Map ? raw.map((k, v) => MapEntry(k.toString(), v)) : <String, Object?>{};
      seen.add(Seen(r.method, r.url.path, body));
      final key = '${r.method} ${r.url.path}';
      final err = errors[key];
      if (err != null) return h.Response(jsonEncode(err.$2), err.$1, headers: _json);
      final a = answers[key];
      if (a == null) return h.Response('{"detail":"no canned answer"}', 404, headers: _json);
      final value = a is Object? Function(Map<String, Object?>) ? a(body) : a;
      return h.Response(jsonEncode(value), 200, headers: _json);
    }),
  );

  static const _json = {'content-type': 'application/json'};
}

/// A JWT with the given `sub` (unsigned; the client only reads it).
String jwt(String sub) {
  String enc(Object o) => base64Url.encode(utf8.encode(jsonEncode(o))).replaceAll('=', '');
  return '${enc({'alg': 'none'})}.${enc({'sub': sub, 'exp': 4102444800})}.sig';
}

/// Records every write, in order, across the access and refresh stores.
class WriteLog {
  final List<String> events = [];
}

class LoggedTokenStore extends InMemoryTokenStore {
  LoggedTokenStore(this.log);
  final WriteLog log;

  @override
  Future<void> save(String token) async {
    log.events.add('access.save');
    await super.save(token);
  }

  @override
  Future<void> clear() async {
    log.events.add('access.clear');
    await super.clear();
  }
}

class LoggedRefreshStore extends InMemoryRefreshTokenStore {
  LoggedRefreshStore(this.log, [super.initial]);
  final WriteLog log;
  int reloads = 0;

  @override
  Future<void> save(String token) async {
    log.events.add('refresh.save');
    await super.save(token);
  }

  @override
  Future<void> clear() async {
    log.events.add('refresh.clear');
    await super.clear();
  }

  @override
  Future<void> reload() async => reloads++;
}
