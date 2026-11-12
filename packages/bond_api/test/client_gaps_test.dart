@Timeout(Duration(seconds: 5))
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

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
  Duration timeout = const Duration(seconds: 60),
  List<String>? events,
  _Tokens? tokens,
}) {
  final t = tokens ?? _Tokens();
  return ApiClient(
    baseUrl: Uri.parse('https://api.test/api/v1'),
    http: MockClient(handler),
    tokens: t,
    timeout: timeout,
    endsSession: endsSession,
    onUnauthorized: () async {
      events?.add('renew');
      t.value = 'new';
      return SessionRefresh.renewed;
    },
    onSessionExpired: () async => events?.add('expired'),
    onSessionRevoked: () async => events?.add('revoked'),
  );
}

void main() {
  group('endsSession', () {
    test('client_401_with_code_not_session_end', () async {
      final events = <String>[];
      var calls = 0;
      final c = _client((r) async {
        calls++;
        return _json({'detail': {'code': 'mail_not_connected', 'message': 'Connect mail'}}, 401);
      }, events: events, endsSession: (e) => e.code == null);
      await expectLater(
        c.getJson('/mail'),
        throwsA(isA<Unauthorized>().having((e) => e.code, 'code', 'mail_not_connected')),
      );
      expect(calls, 1);
      expect(events, isEmpty);
    });

    test('client_401_without_code_still_renews', () async {
      final events = <String>[];
      var calls = 0;
      final c = _client((r) async {
        calls++;
        return r.headers['Authorization'] == 'Bearer new' ? _json({'ok': true}) : _json({'detail': 'expired'}, 401);
      }, events: events, endsSession: (e) => e.message == 'expired');
      expect(await c.getJson('/x'), {'ok': true});
      expect(events, ['renew']);
      expect(calls, 2);
    });

    test('predicate true then a second 401 ends the session', () async {
      final events = <String>[];
      final c = _client((r) async => _json({'detail': 'expired'}, 401), events: events, endsSession: (_) => true);
      await expectLater(c.getJson('/x'), throwsA(isA<Unauthorized>()));
      expect(events, ['renew', 'expired']);
    });

    test('client_default_every_401_ends_session', () async {
      final events = <String>[];
      final c = _client((r) async => _json({'detail': {'code': 'mail_not_connected', 'message': 'm'}}, 401),
          events: events);
      await expectLater(c.getJson('/mail'), throwsA(isA<Unauthorized>()));
      expect(events, ['renew', 'expired']);
    });
  });

  group('requestBytes', () {
    test('request_bytes_posts_json_and_returns_bytes', () async {
      late http.Request seen;
      final c = _client((r) async {
        seen = r;
        return http.Response.bytes([1, 2, 3], 200);
      });
      final out = await c.requestBytes('POST', '/pdf', body: {'a': 1}, query: {'q': 'x'}, accept: 'application/pdf');
      expect(out, Uint8List.fromList([1, 2, 3]));
      expect(seen.method, 'POST');
      expect(seen.url.query, 'q=x');
      expect(jsonDecode(seen.body), {'a': 1});
      expect(seen.headers['Content-Type'], contains('application/json'));
      expect(seen.headers['Accept'], 'application/pdf');
      expect(seen.headers['Authorization'], 'Bearer old');
    });

    test('get_bytes_unchanged', () async {
      late http.Request seen;
      final c = _client((r) async {
        seen = r;
        return http.Response.bytes([9], 200);
      });
      expect(await c.getBytes('/p', query: {'n': 1}), Uint8List.fromList([9]));
      expect(seen.method, 'GET');
      expect(seen.headers['Accept'], '*/*');
      expect(seen.headers.containsKey('Content-Type'), isFalse);
      expect(seen.url.query, 'n=1');
    });

    test('requestBytes maps errors like request', () async {
      final c = _client((r) async => _json({'detail': {'code': 'gone', 'message': 'm'}}, 404));
      await expectLater(c.requestBytes('POST', '/x', body: {}), throwsA(isA<NotFound>()));
    });
  });

  group('per_call_timeout_overrides_default', () {
    Future<http.Response> slow(http.Request r) async {
      await Future<void>.delayed(const Duration(milliseconds: 300));
      return http.Response('{}', 200);
    }

    Matcher timesOut() =>
        throwsA(isA<NetworkFailure>().having((e) => e.kind, 'kind', NetworkFailureKind.timeout));
    const short = Duration(milliseconds: 30);

    test('request', () async {
      final c = _client(slow);
      await expectLater(c.request('GET', '/x', timeout: short), timesOut());
      expect(await c.request('GET', '/x'), isNotNull);
    });
    test('getBytes', () async {
      final c = _client(slow);
      await expectLater(c.getBytes('/x', timeout: short), timesOut());
      expect(await c.getBytes('/x'), isNotEmpty);
    });
    test('requestBytes', () async {
      final c = _client(slow);
      await expectLater(c.requestBytes('POST', '/x', timeout: short), timesOut());
    });
    test('openStream', () async {
      final c = _client(slow);
      await expectLater(c.openStream('GET', '/x', timeout: short), timesOut());
    });
    test('JSON helpers pass it through', () async {
      final c = _client(slow);
      await expectLater(c.getJson('/x', timeout: short), timesOut());
      await expectLater(c.postJson('/x', timeout: short), timesOut());
      await expectLater(c.getJsonList('/x', timeout: short), timesOut());
    });
    test('a longer per-call limit beats a short default', () async {
      final c = _client(slow, timeout: short);
      expect(await c.getJson('/x', timeout: const Duration(seconds: 2)), isEmpty);
    });
  });
}
