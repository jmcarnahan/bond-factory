@Timeout(Duration(seconds: 5))
library;

import 'dart:async';
import 'dart:convert';

import 'package:bond_api/bond_api.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

http.Response _json(Object? body, [int status = 200]) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});

class _Tokens implements TokenSource {
  String? value = 'old';
  @override
  String? get token => value;
}

ApiClient _client(
  Future<http.Response> Function(http.Request) handler, {
  bool Function(ErrorBody)? endsSession,
  Duration headerTimeout = const Duration(seconds: 20),
  List<String>? events,
  List<String>? logs,
}) {
  final t = _Tokens();
  return ApiClient(
    baseUrl: Uri.parse('https://api.test/api/v1'),
    http: MockClient(handler),
    tokens: t,
    headerTimeout: headerTimeout,
    endsSession: endsSession,
    log: logs?.add,
    onUnauthorized: () async {
      events?.add('renew');
      t.value = 'new';
      return SessionRefresh.renewed;
    },
    onSessionExpired: () async => events?.add('expired'),
  );
}

Map<String, Object?> _biz() => {'detail': {'code': 'mail_not_connected', 'message': 'm'}};

void main() {
  test('client_second_401_with_code_not_session_end', () async {
    final events = <String>[];
    // First 401 ends the session (renew), the replay's 401 carries the code.
    final c = _client((r) async {
      return r.headers['Authorization'] == 'Bearer new' ? _json(_biz(), 401) : _json({'detail': 'expired'}, 401);
    }, events: events, endsSession: (e) => e.message == 'expired');
    await expectLater(c.getJson('/x'),
        throwsA(isA<Unauthorized>().having((e) => e.code, 'code', 'mail_not_connected')));
    expect(events, ['renew']); // no 'expired' hook
  });

  test('client_ends_session_throwing_is_logged_and_true', () async {
    final events = <String>[];
    final logs = <String>[];
    final c = _client((r) async => _json({'detail': 'expired'}, 401),
        events: events, logs: logs, endsSession: (_) => throw StateError('boom'));
    await expectLater(c.getJson('/x'), throwsA(isA<Unauthorized>()));
    expect(events, ['renew', 'expired']);
    expect(logs.any((l) => l.contains('endsSession failed')), isTrue);
  });

  group('per-call headerTimeout', () {
    Future<http.Response> slow(http.Request r) async {
      await Future<void>.delayed(const Duration(milliseconds: 150));
      return _json({'ok': true});
    }

    test('fails without it', () async {
      final c = _client(slow, headerTimeout: const Duration(milliseconds: 40));
      await expectLater(c.getJson('/x'), throwsA(isA<NetworkFailure>()));
    });

    test('passes with a longer per-call headerTimeout', () async {
      final c = _client(slow, headerTimeout: const Duration(milliseconds: 40));
      expect(await c.getJson('/x', headerTimeout: const Duration(seconds: 2)), {'ok': true});
      expect(await c.getBytes('/x', headerTimeout: const Duration(seconds: 2)), isNotEmpty);
      final s = await c.openStream('GET', '/x', headerTimeout: const Duration(seconds: 2));
      expect(s.statusCode, 200);
    });
  });
}
