import 'package:bond_api/bond_api.dart';
import 'package:bond_signin/bond_signin.dart';
import 'package:test/test.dart';

import 'support/fakes.dart';

void main() {
  test('startWeb posts redirect_to and mode web and returns the url', () async {
    final s = FakeServer({'POST /auth/signin/google/start': {'url': 'https://idp.test/authorize?x=1'}});
    final url = await SignInApi(s.api).startWeb('google', redirectTo: 'https://app.test/');
    expect(url.toString(), 'https://idp.test/authorize?x=1');
    expect(s.seen.single.body, {'redirect_to': 'https://app.test/', 'mode': 'web'});
  });

  test('startNative sends the challenge, never the secret', () async {
    final s = FakeServer({'POST /auth/signin/microsoft/start': {'url': 'https://idp.test/a'}});
    final (attempt, url) =
        await SignInApi(s.api).startNative('microsoft', returnBase: 'https://api.test/app/return/');
    expect(url.host, 'idp.test');
    final body = s.seen.single.body;
    expect(body['mode'], 'native');
    expect(body['device_challenge'], attempt.deviceChallenge);
    expect(body['attempt'], attempt.id);
    expect(body['redirect_to'], 'https://api.test/app/return/microsoft'); // trailing slash trimmed
    expect(body.values, isNot(contains(attempt.deviceSecret)));
    expect(body.keys.toSet(), {'mode', 'device_challenge', 'attempt', 'redirect_to'});
  });

  test('start without a url is a bad response', () async {
    final s = FakeServer({'POST /auth/signin/google/start': {}});
    expect(SignInApi(s.api).startWeb('google', redirectTo: 'x'), throwsA(isA<BadResponse>()));
  });

  test('redeem posts code and device_secret and returns the body', () async {
    final s = FakeServer({'POST /auth/signin/redeem': {'token': 't', 'refresh_token': 'r', 'user': {}}});
    final a = SignInAttempt.generate();
    final out = await SignInApi(s.api).redeem(a, 'code-1');
    expect(s.seen.single.body, {'code': 'code-1', 'device_secret': a.deviceSecret});
    expect(out['refresh_token'], 'r');
  });

  test('a refused redeem surfaces as an Unauthorized with the code', () async {
    final s = FakeServer()..errors['POST /auth/signin/redeem'] = (401, {'detail': {'code': 'invalid_handoff', 'message': 'no'}});
    final call = SignInApi(s.api).redeem(SignInAttempt.generate(), 'c');
    await expectLater(call, throwsA(isA<Unauthorized>().having((e) => e.code, 'code', 'invalid_handoff')));
  });

  test('providers reads signin, break_glass and default_flow', () async {
    final s = FakeServer({
      'GET /auth/providers': {
        'signin': [{'id': 'google', 'label': 'Google'}],
        'break_glass': true,
        'default_flow': 'signin',
      }
    });
    final p = await SignInApi(s.api).providers();
    expect(p.signin.single.id, 'google');
    expect([p.breakGlass, p.defaultFlow], [true, 'signin']);
  });

  test('SignInClient is the same class', () {
    final s = FakeServer();
    expect(SignInClient(s.api), isA<SignInApi>());
  });
}
