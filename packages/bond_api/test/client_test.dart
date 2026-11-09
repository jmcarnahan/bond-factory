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

Map<String, Object?> _detail(String code, [String message = 'm']) => {
      'detail': {'code': code, 'message': message},
    };

ApiClient _client(
  Future<http.Response> Function(http.Request) handler, {
  TokenSource? tokens,
  Duration? headerTimeout,
  Duration? timeout,
  Future<SessionRefresh> Function()? onUnauthorized,
  Future<void> Function()? onSessionRevoked,
  Future<void> Function()? onSessionExpired,
  Future<void> Function()? onDeactivated,
}) {
  // A runaway retry loop must turn into a red test, not a hang.
  var sent = 0;
  Future<http.Response> guarded(http.Request r) {
    if (++sent > 5) throw StateError('runaway: more than 5 requests for one test');
    return handler(r);
  }

  return ApiClient(
      baseUrl: Uri.parse('https://api.test/api/v1'),
      http: MockClient(guarded),
      tokens: tokens,
      headerTimeout: headerTimeout ?? const Duration(seconds: 20),
      timeout: timeout ?? const Duration(seconds: 60),
      onUnauthorized: onUnauthorized,
      onSessionRevoked: onSessionRevoked,
      onSessionExpired: onSessionExpired,
      onDeactivated: onDeactivated,
    );
}

void main() {
  group('requests', () {
    test('GET joins the base path, adds query and bearer token', () async {
      late http.Request seen;
      final c = _client((r) async {
        seen = r;
        return _json({'ok': true});
      }, tokens: StaticTokenSource('tok'));
      final body = await c.getJson('/items', query: {'q': 'a b', 'skip': null, 'n': 3, 'tag': ['x', 'y']});
      expect(body, {'ok': true});
      expect(seen.method, 'GET');
      expect(seen.url.path, '/api/v1/items');
      expect(seen.url.queryParametersAll, {'q': ['a b'], 'n': ['3'], 'tag': ['x', 'y']});
      expect(seen.headers['Authorization'], 'Bearer tok');
      expect(seen.headers['Accept'], 'application/json');
    });

    test('no token means no Authorization header', () async {
      late http.Request seen;
      final c = _client((r) async {
        seen = r;
        return _json({});
      });
      await c.getJson('items');
      expect(seen.headers.containsKey('Authorization'), isFalse);
      expect(seen.url.path, '/api/v1/items');
    });

    test('post, put, patch and delete send JSON and return maps', () async {
      final seen = <String>[];
      final bodies = <Object?>[];
      final c = _client((r) async {
        seen.add(r.method);
        bodies.add(r.body.isEmpty ? null : jsonDecode(r.body));
        expect(r.headers['Content-Type'], startsWith('application/json'));
        return _json({'m': r.method});
      });
      expect(await c.postJson('/a', body: {'x': 1}), {'m': 'POST'});
      expect(await c.putJson('/a', body: {'x': 2}), {'m': 'PUT'});
      expect(await c.patchJson('/a', body: {'x': 3}), {'m': 'PATCH'});
      expect(await c.deleteJson('/a'), {'m': 'DELETE'});
      expect(seen, ['POST', 'PUT', 'PATCH', 'DELETE']);
      expect(bodies, [{'x': 1}, {'x': 2}, {'x': 3}, null]);
    });

    test('empty body reads as an empty map; lists are supported', () async {
      final c = _client((r) async => r.url.path.endsWith('/list') ? _json([1, 2]) : http.Response('', 204));
      expect(await c.deleteJson('/x'), isEmpty);
      expect(await c.getJsonList('/list'), [1, 2]);
      await expectLater(c.getJson('/list'), throwsA(isA<BadResponse>()));
    });

    test('getBytes returns the raw body', () async {
      final c = _client((r) async => http.Response.bytes([1, 2, 3], 200));
      expect(await c.getBytes('/photo'), [1, 2, 3]);
    });

    test('unparsable JSON is a BadResponse', () async {
      final c = _client((r) async => http.Response('<html>', 200));
      await expectLater(c.getJson('/x'), throwsA(isA<BadResponse>()));
    });
  });

  group('error mapping through the client', () {
    test('both detail forms per status', () async {
      for (final status in [401, 403, 404, 409, 422, 500, 503]) {
        for (final body in <Object?>[
          {'detail': 'plain_reason'},
          _detail('named'),
        ]) {
          final c = _client((r) async => _json(body, status));
          await expectLater(
            c.getJson('/x'),
            throwsA(isA<ApiException>().having((e) => e.statusCode, 'status', status)),
            reason: '$status $body',
          );
        }
      }
    });

    test('code and hint reach the exception', () async {
      final c = _client((r) async => _json({
            'detail': {'code': 'not_invited', 'message': 'No.', 'hint': 'apple_relay'},
          }, 403));
      await expectLater(
        c.postJson('/auth/firebase'),
        throwsA(isA<Forbidden>().having((e) => e.code, 'code', 'not_invited').having((e) => e.hint, 'hint', 'apple_relay')),
      );
    });
  });

  group('timeouts', () {
    test('no headers in time is a timeout failure', () async {
      final never = Completer<http.Response>();
      final c = _client((r) => never.future, headerTimeout: const Duration(milliseconds: 40));
      await expectLater(
        c.getJson('/slow'),
        throwsA(isA<NetworkFailure>().having((e) => e.kind, 'kind', NetworkFailureKind.timeout)),
      );
    });

    test('a connection error is noAnswer', () async {
      final c = _client((r) async => throw http.ClientException('refused'));
      await expectLater(
        c.getJson('/x'),
        throwsA(isA<NetworkFailure>()
            .having((e) => e.kind, 'kind', NetworkFailureKind.noAnswer)
            .having((e) => e.baseUrl, 'baseUrl', 'https://api.test/api/v1')),
      );
    });
  });

  group('body and upload timeouts', () {
    // Headers arrive at once; the body never finishes.
    ApiClient stalled({Duration? timeout, Duration? uploadTimeout}) {
      final stuck = StreamController<List<int>>();
      addTearDown(stuck.close);
      return ApiClient(
        baseUrl: Uri.parse('https://api.test'),
        timeout: timeout ?? const Duration(seconds: 60),
        uploadTimeout: uploadTimeout ?? const Duration(seconds: 120),
        http: MockClient.streaming((req, _) async {
          stuck.add(utf8.encode('{"par'));
          return http.StreamedResponse(stuck.stream, 200, request: req);
        }),
      );
    }

    test('a slow body after the headers hits timeout', () async {
      final c = stalled(timeout: const Duration(milliseconds: 80));
      await expectLater(
        c.getJson('/slow'),
        throwsA(isA<NetworkFailure>().having((e) => e.kind, 'kind', NetworkFailureKind.timeout)),
      );
    });

    test('getBytes with a slow body hits timeout', () async {
      final c = stalled(timeout: const Duration(milliseconds: 80));
      await expectLater(
        c.getBytes('/slow'),
        throwsA(isA<NetworkFailure>().having((e) => e.kind, 'kind', NetworkFailureKind.timeout)),
      );
    });

    test('a multipart whose answer body stalls hits uploadTimeout, not timeout', () async {
      final c = stalled(timeout: const Duration(minutes: 5), uploadTimeout: const Duration(milliseconds: 80));
      final clock = Stopwatch()..start();
      await expectLater(
        c.postMultipart('/up', files: [ApiFile(field: 'f', filename: 'a.csv', bytes: utf8.encode('a'))]),
        throwsA(isA<NetworkFailure>().having((e) => e.kind, 'kind', NetworkFailureKind.timeout)),
      );
      expect(clock.elapsed, lessThan(const Duration(seconds: 4)));
    });

    test('a multipart with no headers in time hits uploadTimeout', () async {
      final never = Completer<http.StreamedResponse>();
      final c = ApiClient(
        baseUrl: Uri.parse('https://api.test'),
        uploadTimeout: const Duration(milliseconds: 80),
        http: MockClient.streaming((req, _) => never.future),
      );
      await expectLater(
        c.postMultipart('/up', fields: {'a': 'b'}),
        throwsA(isA<NetworkFailure>().having((e) => e.kind, 'kind', NetworkFailureKind.timeout)),
      );
    });
  });

  group('401 handling', () {
    test('renewed: replayed exactly once with the new token', () async {
      final tokens = StaticTokenSource('old');
      final seenTokens = <String?>[];
      var renewals = 0;
      final c = _client((r) async {
        seenTokens.add(r.headers['Authorization']);
        return seenTokens.length == 1 ? _json(_detail('invalid_token'), 401) : _json({'ok': 1});
      }, tokens: tokens, onUnauthorized: () async {
        renewals++;
        tokens.token = 'new';
        return SessionRefresh.renewed;
      });
      expect(await c.getJson('/me'), {'ok': 1});
      expect(seenTokens, ['Bearer old', 'Bearer new']);
      expect(renewals, 1);
    });

    test('a slow renewal does not eat the replay budget', () async {
      final tokens = StaticTokenSource('old');
      var calls = 0;
      final c = ApiClient(
        baseUrl: Uri.parse('https://api.test'),
        tokens: tokens,
        timeout: const Duration(milliseconds: 300),
        headerTimeout: const Duration(milliseconds: 300),
        onUnauthorized: () async {
          await Future<void>.delayed(const Duration(milliseconds: 400));
          tokens.token = 'new';
          return SessionRefresh.renewed;
        },
        http: MockClient((r) async {
          calls++;
          if (calls == 1) return _json(_detail('x'), 401);
          await Future<void>.delayed(const Duration(milliseconds: 50)); // a real answer takes time
          return _json({'ok': 1});
        }),
      );
      expect(await c.getJson('/me'), {'ok': 1});
      expect(calls, 2);
    });

    test('a second 401 after renewal is not renewed again', () async {
      final tokens = StaticTokenSource('old');
      var requests = 0;
      var renewals = 0;
      var ended = 0;
      final c = _client((r) async {
        requests++;
        return _json(_detail('invalid_token'), 401);
      }, tokens: tokens, onUnauthorized: () async {
        renewals++;
        tokens.token = 'new$renewals';
        return SessionRefresh.renewed;
      }, onSessionExpired: () async => ended++);
      await expectLater(c.getJson('/me'), throwsA(isA<Unauthorized>().having((e) => e.refreshRejected, 'rejected', false)));
      expect(requests, 2);
      expect(renewals, 1);
      expect(ended, 1);
    });

    test('rejected: Unauthorized(refreshRejected) and the session-over hook', () async {
      var requests = 0;
      var ended = 0;
      final c = _client((r) async {
        requests++;
        return _json(_detail('invalid_token'), 401);
      }, tokens: StaticTokenSource('t'), onUnauthorized: () async => SessionRefresh.rejected, onSessionExpired: () async => ended++);
      await expectLater(c.getJson('/me'), throwsA(isA<Unauthorized>().having((e) => e.refreshRejected, 'rejected', true)));
      expect(requests, 1);
      expect(ended, 1);
    });

    test('offline: NetworkFailure(noAnswer), no session-over hook', () async {
      var ended = 0;
      final c = _client((r) async => _json(_detail('invalid_token'), 401),
          tokens: StaticTokenSource('t'), onUnauthorized: () async => SessionRefresh.offline, onSessionExpired: () async => ended++);
      await expectLater(
        c.getJson('/me'),
        throwsA(isA<NetworkFailure>().having((e) => e.kind, 'kind', NetworkFailureKind.noAnswer)),
      );
      expect(ended, 0);
    });

    test('a hook that throws counts as rejected', () async {
      final c = _client((r) async => _json(_detail('x'), 401),
          tokens: StaticTokenSource('t'), onUnauthorized: () async => throw StateError('boom'));
      await expectLater(c.getJson('/me'), throwsA(isA<Unauthorized>().having((e) => e.refreshRejected, 'rejected', true)));
    });

    test('auth paths are never renewed and fire no hooks', () async {
      for (final path in authPathsExcludedFromRenewal) {
        var renewals = 0;
        var ended = 0;
        var requests = 0;
        final c = _client((r) async {
          requests++;
          return _json(_detail('invalid_token'), 401);
        }, tokens: StaticTokenSource('t'), onUnauthorized: () async {
          renewals++;
          return SessionRefresh.renewed;
        }, onSessionExpired: () async => ended++);
        await expectLater(c.postJson(path), throwsA(isA<Unauthorized>()));
        expect([requests, renewals, ended], [1, 0, 0], reason: path);
      }
    });

    test('no token sent: no renewal', () async {
      var renewals = 0;
      final c = _client((r) async => _json(_detail('x'), 401), onUnauthorized: () async {
        renewals++;
        return SessionRefresh.renewed;
      });
      await expectLater(c.getJson('/me'), throwsA(isA<Unauthorized>()));
      expect(renewals, 0);
    });

    test('concurrent 401s share one renewal', () async {
      final tokens = StaticTokenSource('old');
      var renewals = 0;
      final gate = Completer<void>();
      final c = _client((r) async {
        return r.headers['Authorization'] == 'Bearer old' ? _json(_detail('x'), 401) : _json({'ok': 1});
      }, tokens: tokens, onUnauthorized: () async {
        renewals++;
        await gate.future;
        tokens.token = 'new';
        return SessionRefresh.renewed;
      });
      final a = c.getJson('/a');
      final b = c.getJson('/b');
      await Future<void>.delayed(const Duration(milliseconds: 20));
      gate.complete();
      expect(await Future.wait([a, b]), [{'ok': 1}, {'ok': 1}]);
      expect(renewals, 1);
    });

    test('session_revoked runs onSessionRevoked before onSessionExpired, once', () async {
      final order = <String>[];
      final c = _client((r) async => _json(_detail('session_revoked'), 401),
          tokens: StaticTokenSource('t'),
          onSessionRevoked: () async => order.add('revoked'),
          onSessionExpired: () async => order.add('expired'));
      await expectLater(c.getJson('/a'), throwsA(isA<Unauthorized>().having((e) => e.code, 'code', 'session_revoked')));
      await expectLater(c.getJson('/b'), throwsA(isA<Unauthorized>()));
      expect(order, ['revoked', 'expired']);
    });
  });

  group('403 deactivated', () {
    test('runs onDeactivated once and throws Forbidden', () async {
      var n = 0;
      final c = _client((r) async => _json(_detail('deactivated'), 403),
          tokens: StaticTokenSource('t'), onDeactivated: () async => n++);
      await expectLater(c.getJson('/a'), throwsA(isA<Forbidden>().having((e) => e.code, 'code', 'deactivated')));
      await expectLater(c.getJson('/b'), throwsA(isA<Forbidden>()));
      expect(n, 1);
    });

    test('a success re-arms the hook', () async {
      var n = 0;
      var fail = true;
      final c = _client((r) async => fail ? _json(_detail('deactivated'), 403) : _json({}),
          tokens: StaticTokenSource('t'), onDeactivated: () async => n++);
      await expectLater(c.getJson('/a'), throwsA(isA<Forbidden>()));
      fail = false;
      await c.getJson('/ok');
      fail = true;
      await expectLater(c.getJson('/a'), throwsA(isA<Forbidden>()));
      expect(n, 2);
    });

    test('hooks can be set after construction', () async {
      var n = 0;
      final c = _client((r) async => _json(_detail('deactivated'), 403), tokens: StaticTokenSource('t'));
      c.onDeactivated = () async => n++;
      await expectLater(c.getJson('/a'), throwsA(isA<Forbidden>()));
      expect(n, 1);
    });
  });

  group('multipart', () {
    test('body carries fields and the file', () async {
      late http.Request seen;
      final c = _client((r) async {
        seen = r;
        return _json({'id': 'p1'}, 201);
      }, tokens: StaticTokenSource('t'));
      final out = await c.postMultipart('/photos',
          fields: {'caption': 'roof'},
          files: [ApiFile(field: 'file', filename: 'a.png', bytes: utf8.encode('PNGDATA'))]);
      expect(out, {'id': 'p1'});
      expect(seen.headers['content-type'], startsWith('multipart/form-data; boundary='));
      expect(seen.headers['Authorization'], 'Bearer t');
      expect(seen.body, contains('name="caption"'));
      expect(seen.body, contains('roof'));
      expect(seen.body, contains('name="file"; filename="a.png"'));
      expect(seen.body, contains('content-type: image/png'));
      expect(seen.body, contains('PNGDATA'));
    });

    test('a 401 replays the multipart request with the new token', () async {
      final tokens = StaticTokenSource('old');
      final bodies = <String>[];
      final c = _client((r) async {
        bodies.add(r.body);
        return bodies.length == 1 ? _json(_detail('x'), 401) : _json({'ok': 1});
      }, tokens: tokens, onUnauthorized: () async {
        tokens.token = 'new';
        return SessionRefresh.renewed;
      });
      await c.postMultipart('/up', files: [ApiFile(field: 'f', filename: 'a.csv', bytes: utf8.encode('a,b'))]);
      expect(bodies, hasLength(2));
      expect(bodies.last, contains('a,b'));
    });

    test('guessContentType', () {
      expect(guessContentType('x.JPG'), 'image/jpeg');
      expect(guessContentType('x.pdf'), 'application/pdf');
      expect(guessContentType('x'), isNull);
    });
  });
}
