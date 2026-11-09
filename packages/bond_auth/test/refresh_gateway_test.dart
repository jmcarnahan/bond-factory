import 'dart:async';
import 'dart:convert';

import 'package:bond_api/bond_api.dart';
import 'package:bond_auth/bond_auth.dart';
import 'package:http/http.dart' as http;
import 'package:test/test.dart';

import 'support.dart';

/// Records every write and reload in one shared list, in call order.
class LoggedTokens extends InMemoryTokenStore {
  LoggedTokens(this.log);
  final List<String> log;

  @override
  Future<void> save(String token) async {
    log.add('access.save');
    await super.save(token);
  }

  @override
  Future<void> clear() async {
    log.add('access.clear');
    await super.clear();
  }
}

class LoggedRefresh extends InMemoryRefreshTokenStore {
  LoggedRefresh(this.log, [super.token]);
  final List<String> log;

  @override
  Future<void> save(String token) async {
    log.add('refresh.save');
    await super.save(token);
  }

  @override
  Future<void> clear() async {
    log.add('refresh.clear');
    await super.clear();
  }

  @override
  Future<void> reload() async => log.add('reload');
}

/// A store with a persisted value and a cache, like secure storage in two isolates.
class DiskRefreshStore implements RefreshTokenStore {
  DiskRefreshStore(this.disk);
  final Map<String, String> disk;
  String? _cache;

  @override
  Future<String?> load() async => _cache;
  @override
  Future<void> reload() async => _cache = disk['r'];
  @override
  Future<String?> loadRotation() async => disk['rot'];
  @override
  Future<void> saveRotation(String? id) async {
    if (id == null) {
      disk.remove('rot');
    } else {
      disk['rot'] = id;
    }
  }
  @override
  Future<void> save(String token) async => disk['r'] = _cache = token;
  @override
  Future<void> clear() async {
    disk.remove('r');
    disk.remove('rot');
    _cache = null;
  }
}

/// Persists like [DiskRefreshStore] but its refresh-token write fails (a crash or a full disk).
class FailingSaveStore extends DiskRefreshStore {
  FailingSaveStore(super.disk);
  @override
  Future<void> save(String token) async => throw const TokenStoreException('write refused');
}

/// A native-style gateway: posts the stored refresh token and a rotation id.
class RotatingGateway extends GatewayBase implements AuthGateway {
  RotatingGateway({required super.api, required super.tokens, super.refreshTokens, super.onSessionEnded, super.onStorageFailure, super.authPrefix});

  @override
  Future<AuthSession> exchangeForRefresh(String? expectedUserId) async {
    final refresh = await refreshTokens.load();
    final body = await api.postJson('$authPrefix/refresh', body: {
      'refresh_token': ?refresh,
      'delivery': 'body',
      'rotation_id': rotationIds.current,
    });
    return sessionFromAuthBody(body, path: '$authPrefix/refresh');
  }

  @override
  Future<void> signOut() => endServerSession();

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnsupportedError('${invocation.memberName}');
}

Map<String, Object?> answer(String userId, String refresh, {String? tag}) =>
    {...authBody(userId, tag: tag), 'refresh_token': refresh};

Map<String, Object?> refused(String code) => {
      'detail': {'code': code, 'message': 'no'},
    };

void main() {
  late Server server;
  late List<String> log;
  late LoggedTokens tokens;
  late LoggedRefresh refresh;
  late RotatingGateway gateway;
  final ended = <String>[];

  setUp(() {
    server = Server();
    log = [];
    ended.clear();
    tokens = LoggedTokens(log);
    refresh = LoggedRefresh(log, 'r0');
    tokens.token = 'old';
    gateway = RotatingGateway(api: server.api, tokens: tokens, refreshTokens: refresh, onSessionEnded: ended.add);
  });

  group('refresh sessions', () {
    test('accept saves the refresh token BEFORE the access token', () async {
      final s = await gateway.accept(answer('u1', 'r1'), '/auth/x');
      expect(log, ['refresh.save', 'access.save']);
      expect(await refresh.load(), 'r1');
      expect(s.refreshToken, 'r1');
    });

    test('a renewal also writes the new refresh token first', () async {
      server.json('POST', '/auth/refresh', answer('u1', 'r1'));
      final s = await gateway.refreshSession();
      expect(log, ['reload', 'refresh.save', 'access.save']);
      expect(s!.refreshToken, 'r1');
      expect(tokens.token, s.token);
    });

    test('an answer without refresh_token leaves the refresh slot alone', () async {
      final s = await gateway.accept(authBody('u1'), '/auth/x');
      expect(s.refreshToken, isNull);
      expect(log, ['access.save']);
      expect(await refresh.load(), 'r0');
    });

    test('five concurrent renewals send ONE rotate', () async {
      final gate = Completer<void>();
      server.on('POST', '/auth/refresh', () async {
        await gate.future;
        return http.Response(jsonEncode(answer('u1', 'r1')), 200, headers: {'content-type': 'application/json'});
      });
      final hook = renewalHook(gateway);
      final all = [for (var i = 0; i < 5; i++) hook()];
      await Future<void>.delayed(Duration.zero);
      gate.complete();
      expect(await Future.wait(all), everyElement(SessionRefresh.renewed));
      expect(server.count('POST', '/auth/refresh'), 1);
      expect(await refresh.load(), 'r1');
    });

    test('reload runs before the rotate request', () async {
      server.on('POST', '/auth/refresh', () async {
        log.add('POST');
        return http.Response(jsonEncode(answer('u1', 'r1')), 200, headers: {'content-type': 'application/json'});
      });
      await gateway.refreshSession();
      expect(log.indexOf('reload'), lessThan(log.indexOf('POST')));
    });

    test('two gateways on one store share one token', () async {
      final disk = <String, String>{'r': 'r0'};
      final a = RotatingGateway(api: server.api, tokens: InMemoryTokenStore('x'), refreshTokens: DiskRefreshStore(disk));
      final b = RotatingGateway(api: server.api, tokens: InMemoryTokenStore('x'), refreshTokens: DiskRefreshStore(disk));
      await DiskRefreshStore(disk).reload();
      var n = 0;
      server.on('POST', '/auth/refresh', () async {
        n++;
        return http.Response(jsonEncode(answer('u1', 'r$n')), 200, headers: {'content-type': 'application/json'});
      });
      await a.refreshSession();
      await b.refreshSession();
      expect((server.bodyOf(0)! as Map)['refresh_token'], 'r0');
      expect((server.bodyOf(1)! as Map)['refresh_token'], 'r1');
      expect(disk['r'], 'r2');
    });

    test('offline (no answer, 503, 429) keeps both tokens and reports no end', () async {
      server.fail('POST', '/auth/refresh');
      server.json('POST', '/auth/refresh', {'detail': 'x'}, status: 503);
      server.json('POST', '/auth/refresh', {'detail': 'x'}, status: 429);
      for (var i = 0; i < 3; i++) {
        expect(await gateway.refreshSession(), isNull);
      }
      expect(tokens.token, 'old');
      expect(await refresh.load(), 'r0');
      expect(gateway.lastEndReason, isNull);
      expect(ended, isEmpty);
    });

    for (final code in ['refresh_reused', 'refresh_expired', 'refresh_revoked', 'session_revoked', 'invalid_handoff']) {
      test('401 $code clears both stores and fires onSessionEnded', () async {
        server.json('POST', '/auth/refresh', refused(code), status: 401);
        expect(await renewalHook(gateway)(), SessionRefresh.rejected);
        expect(tokens.token, isNull);
        expect(await refresh.load(), isNull);
        expect(gateway.lastEndReason, code);
        expect(ended, [code]);
      });
    }

    test('a 401 with another code is a refusal but keeps the stores', () async {
      server.json('POST', '/auth/refresh', refused('invalid_token'), status: 401);
      await expectLater(gateway.refreshSession(), throwsA(isA<AuthFailure>()));
      expect(tokens.token, 'old');
      expect(await refresh.load(), 'r0');
      expect(ended, isEmpty);
    });

    test('signed out while the renewal ran: nothing is stored', () async {
      final gate = Completer<void>();
      server.on('POST', '/auth/refresh', () async {
        await gate.future;
        return http.Response(jsonEncode(answer('u1', 'r1')), 200, headers: {'content-type': 'application/json'});
      });
      server.json('POST', '/auth/logout', {'ok': true});
      final pending = gateway.refreshSession();
      await Future<void>.delayed(Duration.zero);
      await gateway.signOut();
      log.clear();
      gate.complete();
      expect(await pending, isNull);
      expect(log, isEmpty);
      expect(tokens.token, isNull);
      expect(await refresh.load(), isNull);
    });

    test('a refresh_reused that lands after sign-out does not report an end', () async {
      final gate = Completer<void>();
      server.on('POST', '/auth/refresh', () async {
        await gate.future;
        return http.Response(jsonEncode(refused('refresh_reused')), 401, headers: {'content-type': 'application/json'});
      });
      server.json('POST', '/auth/logout', {'ok': true});
      final pending = gateway.refreshSession();
      await Future<void>.delayed(Duration.zero);
      await gateway.signOut();
      gate.complete();
      await expectLater(pending, throwsA(isA<AuthFailure>()));
      expect(ended, isEmpty);
      expect(gateway.lastEndReason, isNull);
    });

    test('the rotation id is reused on a retry and replaced after success', () async {
      server.fail('POST', '/auth/refresh');
      server.json('POST', '/auth/refresh', answer('u1', 'r1'));
      server.json('POST', '/auth/refresh', answer('u1', 'r2'));
      expect(await gateway.refreshSession(), isNull);
      await gateway.refreshSession();
      await gateway.refreshSession();
      String id(int i) => (server.bodyOf(i)! as Map)['rotation_id']! as String;
      expect(id(1), id(0));
      expect(id(2), isNot(id(1)));
      expect(id(0), matches(RegExp(r'^[0-9a-f]{32}$')));
    });

    test('signOut sends the refresh token in the logout body and clears both', () async {
      server.json('POST', '/auth/logout', {'ok': true});
      await gateway.signOut();
      expect(server.bodyOf(0), {'refresh_token': 'r0'});
      expect(tokens.token, isNull);
      expect(await refresh.load(), isNull);
    });

    test('signOut without a refresh token posts no body', () async {
      server.json('POST', '/auth/logout', {'ok': true});
      final g = RotatingGateway(api: server.api, tokens: tokens);
      await g.signOut();
      expect(server.requests.single.body, isEmpty);
    });

    test('a new sign-in clears lastEndReason', () async {
      server.json('POST', '/auth/refresh', refused('refresh_reused'), status: 401);
      await renewalHook(gateway)();
      expect(gateway.lastEndReason, 'refresh_reused');
      await gateway.accept(answer('u1', 'r9'), '/auth/x');
      expect(gateway.lastEndReason, isNull);
    });
  });

  group('rotation id persistence', () {
    String idOf(int i) => (server.bodyOf(i)! as Map)['rotation_id']! as String;

    test('a crash after the server rotated: a new gateway on the same store retries with the same id', () async {
      final disk = <String, String>{'r': 'r0'};
      final failures = <Object>[];
      server.json('POST', '/auth/refresh', answer('u1', 'r1'));
      server.json('POST', '/auth/refresh', answer('u1', 'r1b'));
      final a = RotatingGateway(
        api: server.api,
        tokens: InMemoryTokenStore('x'),
        refreshTokens: FailingSaveStore(disk),
        onStorageFailure: failures.add,
      );
      final s = await a.refreshSession();
      expect(s!.refreshToken, 'r1'); // the in-memory session survives the failed write
      expect(failures.single, isA<TokenStoreException>());
      expect(disk['r'], 'r0'); // the new refresh token never reached the disk
      expect(disk['rot'], idOf(0)); // but the rotation id did, before the request

      final b = RotatingGateway(api: server.api, tokens: InMemoryTokenStore('x'), refreshTokens: DiskRefreshStore(disk));
      await b.refreshSession();
      expect(idOf(1), idOf(0));
      expect(disk['rot'], isNull); // stored success clears it
      expect(disk['r'], 'r1b');
    });

    test('a stored success saves null and the next rotation gets a new id', () async {
      final store = InMemoryRefreshTokenStore('r0');
      final g = RotatingGateway(api: server.api, tokens: InMemoryTokenStore('x'), refreshTokens: store);
      server.json('POST', '/auth/refresh', answer('u1', 'r1'));
      await g.refreshSession();
      expect(await store.loadRotation(), isNull);
      await g.refreshSession();
      expect(idOf(1), isNot(idOf(0)));
    });

    test('the id is saved before the request goes out', () async {
      final store = InMemoryRefreshTokenStore('r0');
      final g = RotatingGateway(api: server.api, tokens: InMemoryTokenStore('x'), refreshTokens: store);
      String? seen;
      server.on('POST', '/auth/refresh', () async {
        seen = await store.loadRotation();
        return http.Response(jsonEncode(answer('u1', 'r1')), 200, headers: {'content-type': 'application/json'});
      });
      await g.refreshSession();
      expect(seen, idOf(0));
    });

    test('a failing write in accept keeps the session and reports', () async {
      final failures = <Object>[];
      final g = RotatingGateway(
        api: server.api,
        tokens: InMemoryTokenStore(),
        refreshTokens: FailingSaveStore(<String, String>{}),
        onStorageFailure: failures.add,
      );
      final s = await g.accept(answer('u1', 'r1'), '/auth/x');
      expect(s.userId, 'u1');
      expect(failures, hasLength(1));
    });

    test('a final end code clears the saved rotation id too', () async {
      final store = InMemoryRefreshTokenStore('r0');
      final g = RotatingGateway(api: server.api, tokens: InMemoryTokenStore('x'), refreshTokens: store);
      server.json('POST', '/auth/refresh', refused('refresh_revoked'), status: 401);
      await renewalHook(g)();
      expect(await store.loadRotation(), isNull);
    });
  });

  group('authPrefix', () {
    const p = '/api/v1/auth';

    test('logout, providers, firebase and demo use the prefix; the default stays /auth', () async {
      server.json('POST', '$p/logout', {'ok': true});
      server.json('GET', '$p/providers', {'signin': []});
      final g = RotatingGateway(api: server.api, tokens: tokens, refreshTokens: refresh, authPrefix: p);
      await g.signOut();
      await g.providers();
      expect(server.count('POST', '$p/logout'), 1);
      expect(server.count('GET', '$p/providers'), 1);

      server.json('POST', '$p/firebase', authBody('u1'));
      final fb = FirebaseAuthGateway(
        api: server.api,
        tokens: InMemoryTokenStore(),
        source: FakeIdTokenSource(),
        authPrefix: p,
      );
      await fb.signInWithIdToken('mock:a@example.com');
      expect(server.count('POST', '$p/firebase'), 1);

      server.json('POST', '$p/demo', authBody('u1'));
      await DemoAuthGateway(api: server.api, tokens: InMemoryTokenStore(), authPrefix: p).signInDemo('u1');
      expect(server.count('POST', '$p/demo'), 1);

      server.json('POST', '/auth/logout', {'ok': true});
      await RotatingGateway(api: server.api, tokens: tokens).signOut();
      expect(server.count('POST', '/auth/logout'), 1);
    });

    test('renewal posts to the prefixed refresh path, and a 401 there does not renew again', () async {
      server.json('POST', '$p/refresh', refused('refresh_revoked'), status: 401);
      var hookCalls = 0;
      final api = ApiClient(
        baseUrl: Uri.parse('http://test.invalid'),
        http: server.client,
        tokens: tokens,
        onUnauthorized: () async {
          hookCalls++;
          return SessionRefresh.rejected;
        },
      );
      final g = RotatingGateway(api: api, tokens: tokens, refreshTokens: refresh, authPrefix: p);
      await expectLater(g.refreshSession(), throwsA(isA<AuthFailure>()));
      expect(server.count('POST', '$p/refresh'), 1);
      expect(hookCalls, 0); // bond_api treats the suffix /auth/refresh as an auth path
    });
  });

  group('LiveTokenForgetter', () {
    test('clears both slots, then calls onForgotten', () async {
      var called = false;
      await LiveTokenForgetter(tokens, refreshTokens: refresh, onForgotten: () => called = true).forget();
      expect(tokens.token, isNull);
      expect(await refresh.load(), isNull);
      expect(called, isTrue);
    });

    test('works with the one-string store alone', () async {
      await LiveTokenForgetter(tokens).forget();
      expect(tokens.token, isNull);
    });
  });

  group('RotationIds', () {
    test('stable until succeeded, then new; 32 hex chars', () {
      final ids = RotationIds();
      final a = ids.current;
      expect(ids.current, a);
      expect(a, matches(RegExp(r'^[0-9a-f]{32}$')));
      ids.succeeded();
      expect(ids.current, isNot(a));
    });
  });

  test('sessionFromAuthBody reads refresh_token; null when absent or empty', () {
    expect(sessionFromAuthBody(answer('u1', 'rr')).refreshToken, 'rr');
    expect(sessionFromAuthBody(authBody('u1')).refreshToken, isNull);
    expect(sessionFromAuthBody({...authBody('u1'), 'refresh_token': ''}).refreshToken, isNull);
  });
}
