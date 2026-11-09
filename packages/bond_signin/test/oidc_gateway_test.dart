import 'package:bond_auth/bond_auth.dart';
import 'package:bond_signin/bond_signin.dart';
import 'package:test/test.dart';

import 'support/fakes.dart';

Map<String, Object?> sessionBody(String user, {String? refresh}) => {
      'token': jwt(user),
      'refresh_token': ?refresh,
      'user': {'id': user, 'capabilities': <String>[]},
    };

void main() {
  test('completeWeb posts {} and stores the access token only', () async {
    final s = FakeServer({'POST /auth/refresh': sessionBody('u1')});
    final tokens = InMemoryTokenStore();
    final g = OidcAuthGateway(api: s.api, tokens: tokens);
    final session = await g.completeWeb();
    expect(s.seen.single.body, isEmpty);
    expect(session.userId, 'u1');
    expect(tokens.token, session.token);
  });

  test('completeWeb maps a refusal to AuthFailure', () async {
    final s = FakeServer()..errors['POST /auth/refresh'] = (401, {'detail': {'code': 'refresh_revoked'}});
    final g = OidcAuthGateway(api: s.api, tokens: InMemoryTokenStore());
    await expectLater(g.completeWeb(), throwsA(isA<AuthFailure>().having((e) => e.code, 'code', 'refresh_revoked')));
  });

  test('completeNative redeems with the device secret and saves refresh before access', () async {
    final s = FakeServer({'POST /auth/signin/redeem': sessionBody('u2', refresh: 'rt-1')});
    final log = WriteLog();
    final g = OidcAuthGateway(api: s.api, tokens: LoggedTokenStore(log), refreshTokens: LoggedRefreshStore(log));
    final a = SignInAttempt.generate();
    final session = await g.completeNative(a, 'code-9');
    expect(s.seen.single.body, {'code': 'code-9', 'device_secret': a.deviceSecret});
    expect(log.events, ['refresh.save', 'access.save']);
    expect(session.refreshToken, 'rt-1');
    expect(await g.refreshTokens.load(), 'rt-1');
  });

  test('renewal with a stored token posts body delivery with a rotation id', () async {
    final s = FakeServer({'POST /auth/refresh': sessionBody('u1', refresh: 'rt-2')});
    final refresh = InMemoryRefreshTokenStore('rt-1');
    final g = OidcAuthGateway(api: s.api, tokens: InMemoryTokenStore(), refreshTokens: refresh);
    final session = await g.refreshSession(expectedUserId: 'u1');
    expect(session, isNotNull);
    final b = s.seen.single.body;
    expect([b['refresh_token'], b['delivery']], ['rt-1', 'body']);
    expect(b['rotation_id'], matches(RegExp(r'^[0-9a-f]{32}$')));
    expect(await refresh.load(), 'rt-2'); // the rotated token replaced the old one
  });

  test('renewal on web (no store) sends no refresh token and no delivery', () async {
    final s = FakeServer({'POST /auth/refresh': sessionBody('u1')});
    final g = OidcAuthGateway(api: s.api, tokens: InMemoryTokenStore());
    await g.refreshSession();
    final b = s.seen.single.body;
    expect(b.containsKey('refresh_token'), isFalse);
    expect(b.containsKey('delivery'), isFalse);
  });

  test('a lost answer retries with the same rotation id', () async {
    final s = FakeServer({'POST /auth/refresh': sessionBody('u1', refresh: 'rt-2')});
    s.errors['POST /auth/refresh'] = (503, {'detail': 'down'});
    final g = OidcAuthGateway(api: s.api, tokens: InMemoryTokenStore(), refreshTokens: InMemoryRefreshTokenStore('rt-1'));
    expect(await g.refreshSession(), isNull); // offline keeps the session
    s.errors.clear();
    await g.refreshSession();
    expect(s.seen[0].body['rotation_id'], s.seen[1].body['rotation_id']);
  });

  test('reuse ends the session: both stores cleared, callback fired', () async {
    final s = FakeServer()..errors['POST /auth/refresh'] = (401, {'detail': {'code': 'refresh_reused'}});
    final log = WriteLog();
    String? ended;
    final g = OidcAuthGateway(
      api: s.api,
      tokens: LoggedTokenStore(log),
      refreshTokens: LoggedRefreshStore(log, 'rt-1'),
      onSessionEnded: (c) => ended = c,
    );
    await expectLater(g.refreshSession(), throwsA(isA<AuthFailure>()));
    expect(ended, 'refresh_reused');
    expect(g.lastEndReason, 'refresh_reused');
    expect(log.events, containsAll(['refresh.clear', 'access.clear']));
    expect(await g.refreshTokens.load(), isNull);
  });

  test('two gateways on one store reload before rotating', () async {
    final s = FakeServer({'POST /auth/refresh': sessionBody('u1', refresh: 'rt-2')});
    final store = LoggedRefreshStore(WriteLog(), 'rt-1');
    final a = OidcAuthGateway(api: s.api, tokens: InMemoryTokenStore(), refreshTokens: store);
    final b = OidcAuthGateway(api: s.api, tokens: InMemoryTokenStore(), refreshTokens: store);
    await a.refreshSession();
    await b.refreshSession();
    expect(store.reloads, 2);
    expect(s.seen[1].body['refresh_token'], 'rt-2'); // b saw what a stored
  });

  test('signOut posts the refresh token when present, then clears both', () async {
    final s = FakeServer({'POST /auth/logout': {'status': 'logged_out'}});
    final log = WriteLog();
    final g = OidcAuthGateway(api: s.api, tokens: LoggedTokenStore(log), refreshTokens: LoggedRefreshStore(log, 'rt-1'));
    await g.signOut();
    expect(s.seen.single.body, {'refresh_token': 'rt-1'});
    expect(log.events, containsAll(['refresh.clear', 'access.clear']));
  });

  test('signOut on web posts no body', () async {
    final s = FakeServer({'POST /auth/logout': {'status': 'logged_out'}});
    await OidcAuthGateway(api: s.api, tokens: InMemoryTokenStore()).signOut();
    expect(s.seen.single.body, isEmpty);
  });

  test('e-mail and password methods are unsupported', () async {
    final g = OidcAuthGateway(api: FakeServer().api, tokens: InMemoryTokenStore());
    await expectLater(g.signInWithEmail('a', 'b'), throwsUnsupportedError);
    await expectLater(g.signInWithIdToken('t'), throwsUnsupportedError);
    await expectLater(g.signInDemo('u'), throwsUnsupportedError);
    await expectLater(g.sendPasswordReset('a'), throwsUnsupportedError);
    await expectLater(g.changePassword('a', 'b'), throwsUnsupportedError);
    expect(await g.linkedProviders(), isEmpty);
  });
}
