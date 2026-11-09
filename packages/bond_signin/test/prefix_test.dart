import 'package:bond_auth/bond_auth.dart';
import 'package:bond_signin/bond_signin.dart';
import 'package:test/test.dart';

import 'support/fakes.dart';

void main() {
  const p = '/api/v1/auth';
  final body = {'token': jwt('u1'), 'refresh_token': 'rt-2', 'user': {'id': 'u1'}};

  test('SignInApi derives every route from the prefix', () async {
    final s = FakeServer({
      'POST $p/signin/google/start': {'url': 'https://idp.test/a'},
      'POST $p/signin/redeem': body,
      'GET $p/providers': {'signin': <Object?>[]},
    });
    final api = SignInApi(s.api, prefix: p);
    await api.startWeb('google', redirectTo: 'https://app.test/');
    await api.startNative('google', returnUrl: Uri.parse('https://api.test/app/return/google'));
    await api.redeem(SignInAttempt.generate(), 'c');
    await api.providers();
    expect(s.seen.map((e) => e.path), ['$p/signin/google/start', '$p/signin/google/start', '$p/signin/redeem', '$p/providers']);
    expect(s.seen[1].body['redirect_to'], 'https://api.test/app/return/google'); // unchanged
  });

  test('OidcAuthGateway completes, renews and lists providers under the prefix', () async {
    final s = FakeServer({
      'POST $p/refresh': body,
      'POST $p/signin/redeem': body,
      'GET $p/providers': {'signin': <Object?>[], 'default_flow': 'signin'},
      'POST $p/logout': {'status': 'logged_out'},
    });
    final g = OidcAuthGateway(api: s.api, tokens: InMemoryTokenStore(), refreshTokens: InMemoryRefreshTokenStore('rt-1'), authPrefix: p);
    await g.completeWeb();
    await g.refreshSession();
    await g.completeNative(SignInAttempt.generate(), 'c');
    expect((await g.providers()).defaultFlow, 'signin');
    await g.signOut();
    expect(s.seen.map((e) => e.path), ['$p/refresh', '$p/refresh', '$p/signin/redeem', '$p/providers', '$p/logout']);
  });
}
