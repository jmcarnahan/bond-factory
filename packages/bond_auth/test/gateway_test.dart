import 'dart:async';
import 'dart:convert';

import 'package:bond_api/bond_api.dart';
import 'package:bond_auth/bond_auth.dart';
import 'package:http/http.dart' as http;
import 'package:test/test.dart';

import 'support.dart';

void main() {
  late Server server;
  late InMemoryTokenStore tokens;

  setUp(() {
    server = Server();
    tokens = InMemoryTokenStore();
  });

  group('DemoAuthGateway', () {
    late DemoAuthGateway gateway;
    setUp(() => gateway = DemoAuthGateway(api: server.api, tokens: tokens));

    test('signInDemo posts the user id and saves the token', () async {
      final body = authBody('u1', caps: ['a', 'b']);
      server.json('POST', '/auth/demo', body);
      final s = await gateway.signInDemo('u1');
      expect(server.bodyOf(0), {'user_id': 'u1'});
      expect(tokens.token, body['token']);
      expect(s.userId, 'u1');
      expect(s.capabilities, ['a', 'b']);
      expect(s.user['email'], 'u1@example.com');
    });

    test('a 404 (demo off) becomes an AuthFailure and stores nothing', () async {
      server.json('POST', '/auth/demo', {'detail': {'code': 'not_found', 'message': 'off'}}, status: 404);
      await expectLater(gateway.signInDemo('u1'), throwsA(isA<AuthFailure>()));
      expect(tokens.token, isNull);
    });

    test('refresh signs in again as the stored user', () async {
      tokens.token = jwt({'sub': 'u1'});
      server.json('POST', '/auth/demo', authBody('u1', tag: 'new'));
      final s = await gateway.refreshSession();
      expect(s!.userId, 'u1');
      expect(server.bodyOf(0), {'user_id': 'u1'});
    });

    test('refresh without any session is refused', () async {
      await expectLater(gateway.refreshSession(), throwsA(isA<AuthFailure>()));
    });

    test('signOut posts logout, ignores its failure and clears', () async {
      tokens.token = 't';
      server.json('POST', '/auth/logout', {'detail': 'x'}, status: 500);
      await gateway.signOut();
      expect(server.count('POST', '/auth/logout'), 1);
      expect(tokens.token, isNull);
    });

    test('two concurrent refreshes make one /auth/demo request', () async {
      tokens.token = jwt({'sub': 'u1'});
      final gate = Completer<void>();
      server.on('POST', '/auth/demo', () async {
        await gate.future;
        return http.Response(jsonEncode(authBody('u1')), 200, headers: {'content-type': 'application/json'});
      });
      final a = gateway.refreshSession();
      final b = gateway.refreshSession();
      await Future<void>.delayed(Duration.zero);
      gate.complete();
      await Future.wait([a, b]);
      expect(server.count('POST', '/auth/demo'), 1);
    });

    test('a 503 on refresh is offline, not a refusal', () async {
      tokens.token = jwt({'sub': 'u1'});
      server.json('POST', '/auth/demo', {'detail': 'x'}, status: 503);
      expect(await gateway.refreshSession(), isNull);
      expect(tokens.token, isNotNull);
    });

    test('a refresh that finishes after signOut stores nothing', () async {
      tokens.token = jwt({'sub': 'u1'});
      final gate = Completer<void>();
      server.on('POST', '/auth/demo', () async {
        await gate.future;
        return http.Response(jsonEncode(authBody('u1')), 200, headers: {'content-type': 'application/json'});
      });
      server.json('POST', '/auth/logout', {'status': 'logged_out'});
      final flight = gateway.refreshSession();
      await Future<void>.delayed(Duration.zero);
      await gateway.signOut();
      gate.complete();
      expect(await flight, isNull);
      expect(tokens.token, isNull);
    });

    test('providers reads the providers answer', () async {
      server.json('GET', '/auth/providers', {'demo': true, 'mock': true});
      final p = await gateway.providers();
      expect(p.demo && p.mock, isTrue);
    });
  });

  group('FirebaseAuthGateway', () {
    late FakeIdTokenSource source;
    late FirebaseAuthGateway gateway;
    setUp(() {
      source = FakeIdTokenSource(token: 'mock:a@example.com');
      gateway = FirebaseAuthGateway(api: server.api, tokens: tokens, source: source);
    });

    test('signInWithIdToken exchanges the id token and saves the session', () async {
      final body = authBody('u1');
      server.json('POST', '/auth/firebase', body);
      final s = await gateway.signInWithIdToken('id-1');
      expect(server.bodyOf(0), {'id_token': 'id-1'});
      expect(tokens.token, body['token']);
      expect(s.userId, 'u1');
    });

    test('signIn false is passed on', () async {
      server.json('POST', '/auth/firebase', authBody('u1'));
      await gateway.signInWithIdToken('id-1', signIn: false);
      expect(server.bodyOf(0), {'id_token': 'id-1', 'sign_in': false});
    });

    test('signInWithEmail goes through the source then the exchange', () async {
      server.json('POST', '/auth/firebase', authBody('u1'));
      await gateway.signInWithEmail('B@example.com', 'pw');
      expect(server.bodyOf(0), {'id_token': 'mock:b@example.com'});
    });

    test('not_invited is an AuthFailure with the code', () async {
      server.json('POST', '/auth/firebase',
          {'detail': {'code': 'not_invited', 'message': 'No invite'}}, status: 403);
      await expectLater(
        gateway.signInWithIdToken('x'),
        throwsA(isA<AuthFailure>()
            .having((e) => e.reason, 'reason', AuthFailureReason.notInvited)
            .having((e) => e.code, 'code', 'not_invited')),
      );
      expect(tokens.token, isNull);
    });

    test('refresh forces a fresh id token and posts it', () async {
      server.json('POST', '/auth/refresh', authBody('u1', tag: 'r'));
      final s = await gateway.refreshSession(expectedUserId: 'u1');
      expect(source.calls, ['currentIdToken(force)']);
      expect(server.bodyOf(0), {'id_token': 'mock:a@example.com'});
      expect(tokens.token, s!.token);
    });

    test('two concurrent refreshes make one request', () async {
      final gate = Completer<void>();
      server.on('POST', '/auth/refresh', () async {
        await gate.future;
        return http.Response('{"token":"${authBody('u1')['token']}","user":{"id":"u1"}}', 200,
            headers: {'content-type': 'application/json'});
      });
      final a = gateway.refreshSession();
      final b = gateway.refreshSession();
      await Future<void>.delayed(Duration.zero);
      gate.complete();
      final results = await Future.wait([a, b]);
      expect(server.count('POST', '/auth/refresh'), 1);
      expect(results[0]!.token, results[1]!.token);
      // The flight is over: the next call is a new request.
      server.json('POST', '/auth/refresh', authBody('u1'));
      await gateway.refreshSession();
      expect(server.count('POST', '/auth/refresh'), 2);
    });

    test('a refresh that finishes after signOut stores nothing and returns null', () async {
      final gate = Completer<void>();
      server.on('POST', '/auth/refresh', () async {
        await gate.future;
        return http.Response(jsonEncode(authBody('u1')), 200, headers: {'content-type': 'application/json'});
      });
      server.json('POST', '/auth/logout', {'status': 'logged_out'});
      final flight = gateway.refreshSession();
      await Future<void>.delayed(Duration.zero);
      await gateway.signOut();
      gate.complete();
      expect(await flight, isNull);
      expect(tokens.token, isNull);
    });

    test('the single flight is keyed by expectedUserId', () async {
      final gate = Completer<void>();
      server.on('POST', '/auth/refresh', () async {
        await gate.future;
        return http.Response(jsonEncode(authBody('u1')), 200, headers: {'content-type': 'application/json'});
      });
      final mine = gateway.refreshSession(expectedUserId: 'u1');
      final theirs = gateway.refreshSession(expectedUserId: 'u2');
      final refused = expectLater(theirs, throwsA(isA<SessionBelongsToAnotherPerson>()));
      await Future<void>.delayed(Duration.zero);
      gate.complete();
      expect((await mine)!.userId, 'u1');
      await refused;
      expect(server.count('POST', '/auth/refresh'), 2);
    });

    test('a rate-limited identity provider is offline, not a refusal', () async {
      tokens.token = 'mine';
      source.failWith = const AuthFailure(AuthFailureReason.rateLimited);
      expect(await gateway.refreshSession(), isNull);
      expect(tokens.token, 'mine');
    });

    test('another person: exception and the store is unchanged', () async {
      tokens.token = 'mine';
      server.json('POST', '/auth/refresh', authBody('someone-else'));
      await expectLater(
        gateway.refreshSession(expectedUserId: 'u1'),
        throwsA(isA<SessionBelongsToAnotherPerson>().having((e) => e.userId, 'userId', 'someone-else')),
      );
      expect(tokens.token, 'mine');
    });

    test('offline gives null and keeps the token', () async {
      tokens.token = 'mine';
      server.fail('POST', '/auth/refresh');
      expect(await gateway.refreshSession(), isNull);
      expect(tokens.token, 'mine');
    });

    test('a 5xx or 429 gives null (offline), a 401 is a refusal', () async {
      server.json('POST', '/auth/refresh', {'detail': 'x'}, status: 503);
      expect(await gateway.refreshSession(), isNull);
      final busy = Server()..json('POST', '/auth/refresh', {'detail': 'x'}, status: 429);
      final b = FirebaseAuthGateway(api: busy.api, tokens: tokens, source: source);
      expect(await b.refreshSession(), isNull);
      final other = Server()..json('POST', '/auth/refresh', {'detail': 'invalid_token'}, status: 401);
      final g = FirebaseAuthGateway(api: other.api, tokens: tokens, source: source);
      await expectLater(g.refreshSession(), throwsA(isA<AuthFailure>()));
    });

    test('a provider with no session is a refusal; a network failure there is offline', () async {
      source.token = null;
      await expectLater(gateway.refreshSession(), throwsA(isA<AuthFailure>()));
      source.failWith = const AuthFailure(AuthFailureReason.network);
      expect(await gateway.refreshSession(), isNull);
      expect(server.requests, isEmpty);
    });

    test('signOut with an unconfigured source still clears the token and does not throw', () async {
      tokens.token = 't';
      server.json('POST', '/auth/logout', {'status': 'logged_out'});
      final g = FirebaseAuthGateway(api: server.api, tokens: tokens, source: const NotConfiguredIdTokenSource());
      await g.signOut();
      expect(tokens.token, isNull);
    });

    test('signOut posts logout, clears the store and signs the provider out', () async {
      tokens.token = 't';
      server.json('POST', '/auth/logout', {'status': 'logged_out'});
      await gateway.signOut();
      expect(tokens.token, isNull);
      expect(source.calls, ['signOut']);
    });
  });

  group('renewalHook', () {
    test('maps the outcomes', () async {
      final source = FakeIdTokenSource(token: 'mock:a@example.com');
      final g = FirebaseAuthGateway(api: server.api, tokens: tokens, source: source);
      server.json('POST', '/auth/refresh', authBody('u1'));
      expect(await renewalHook(g)(), SessionRefresh.renewed);
      expect(await renewalHook(g, expectedUserId: 'other')(), SessionRefresh.rejected);
      source.token = null;
      expect(await renewalHook(g)(), SessionRefresh.rejected);
      source.failWith = const AuthFailure(AuthFailureReason.network);
      expect(await renewalHook(g)(), SessionRefresh.offline);
    });

    test('two requests that both get a 401 share one renewal and both succeed', () async {
      final source = FakeIdTokenSource(token: 'mock:a@example.com');
      tokens.token = 'broken';
      final api = ApiClient(baseUrl: Uri.parse('http://test.invalid'), http: server.client, tokens: tokens);
      final g = FirebaseAuthGateway(api: api, tokens: tokens, source: source);
      api.onUnauthorized = renewalHook(g);
      // Two 401s first, then the answer for every replay.
      server.json('GET', '/auth/me', {'detail': {'code': 'invalid_token', 'message': 'bad'}}, status: 401);
      server.json('GET', '/auth/me', {'detail': {'code': 'invalid_token', 'message': 'bad'}}, status: 401);
      server.json('GET', '/auth/me', {'id': 'u1'});
      server.on('POST', '/auth/refresh', () async {
        await Future<void>.delayed(const Duration(milliseconds: 50));
        return http.Response(jsonEncode(authBody('u1')), 200, headers: {'content-type': 'application/json'});
      });

      final answers = await Future.wait([api.getJson('/auth/me'), api.getJson('/auth/me')]);

      expect(answers.map((a) => a['id']), ['u1', 'u1']);
      expect(server.count('POST', '/auth/refresh'), 1);
      expect(server.count('GET', '/auth/me'), 4);
    });

    test('a dead connection maps to offline', () async {
      server.fail('POST', '/auth/refresh');
      final g = FirebaseAuthGateway(
        api: server.api,
        tokens: tokens,
        source: FakeIdTokenSource(token: 'mock:a@example.com'),
      );
      expect(await renewalHook(g)(), SessionRefresh.offline);
    });

    test('works as ApiClient.onUnauthorized: one renewal, then the replay succeeds', () async {
      final source = FakeIdTokenSource(token: 'mock:a@example.com');
      tokens.token = 'broken';
      final api = ApiClient(baseUrl: Uri.parse('http://test.invalid'), http: server.client, tokens: tokens);
      final g = FirebaseAuthGateway(api: api, tokens: tokens, source: source);
      api.onUnauthorized = renewalHook(g);
      server.json('GET', '/auth/me', {'detail': {'code': 'invalid_token', 'message': 'bad'}}, status: 401);
      server.json('GET', '/auth/me', {'id': 'u1'});
      server.json('POST', '/auth/refresh', authBody('u1'));
      final me = await api.getJson('/auth/me');
      expect(me['id'], 'u1');
      expect(server.count('POST', '/auth/refresh'), 1);
      expect(server.count('GET', '/auth/me'), 2);
    });
  });
}
