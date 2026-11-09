import 'dart:async';
import 'dart:convert';

import 'package:bond_api/bond_api.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// Builds an unsigned JWT with [claims] (the client never verifies it).
String jwt(Map<String, Object?> claims) {
  String part(Object o) => base64Url.encode(utf8.encode(jsonEncode(o))).replaceAll('=', '');
  return '${part({'alg': 'none'})}.${part(claims)}.sig';
}

/// `{token, user}` as the server answers sign-in and refresh.
Map<String, Object?> authBody(String userId, {List<String> caps = const ['tasks.read'], String? tag}) => {
      'token': jwt({'sub': userId, 'capabilities': caps, 'tag': tag ?? '', 'exp': 4102444800}),
      'user': {'id': userId, 'email': '$userId@example.com', 'name': 'Name $userId', 'capabilities': caps},
    };

/// A scriptable server: queue answers per `METHOD /path`; the last repeats.
class Server {
  final Map<String, List<Future<http.Response> Function()>> _queues = {};
  final List<http.Request> requests = [];

  late final MockClient client = MockClient((request) async {
    requests.add(request);
    final queue = _queues['${request.method} ${request.url.path}'];
    if (queue == null || queue.isEmpty) return http.Response('{"detail":"no answer"}', 404);
    return (queue.length > 1 ? queue.removeAt(0) : queue.first)();
  });

  late final ApiClient api = ApiClient(baseUrl: Uri.parse('http://test.invalid'), http: client);

  void json(String method, String path, Object? body, {int status = 200}) => on(
        method,
        path,
        () async => http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'}),
      );

  void on(String method, String path, Future<http.Response> Function() answer) =>
      _queues.putIfAbsent('$method $path', () => []).add(answer);

  void fail(String method, String path) =>
      on(method, path, () async => throw http.ClientException('connection refused'));

  int count(String method, String path) =>
      requests.where((r) => r.method == method && r.url.path == path).length;

  Object? bodyOf(int i) => jsonDecode(requests[i].body);
}
