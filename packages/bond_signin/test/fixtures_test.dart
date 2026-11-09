import 'package:bond_api/bond_api.dart';
import 'package:bond_auth/bond_auth.dart';
import 'package:bond_signin/bond_signin.dart';
import 'package:test/test.dart';

import 'support/fakes.dart';
import 'support/fixtures.dart';

void main() {
  test('startWeb sends exactly the fixture body and reads start_response', () async {
    final s = FakeServer({'POST /auth/signin/google/start': signinMap('start_response')});
    final req = signinMap('start_request_web');
    final url = await SignInApi(s.api).startWeb('google', redirectTo: req['redirect_to']! as String);
    expect(s.seen.single.body, req);
    expect(url.toString(), signinMap('start_response')['url']);
  });

  test('startNative sends the fixture keys, mode, attempt shape and return address', () async {
    final s = FakeServer({'POST /auth/signin/google/start': signinMap('start_response')});
    final req = signinMap('start_request_native');
    final (attempt, _) = await SignInApi(s.api).startNative('google', returnUrl: Uri.parse(req['redirect_to']! as String));
    final sent = s.seen.single.body;
    expect(sent.keys.toSet(), req.keys.toSet());
    expect(sent['redirect_to'], req['redirect_to']);
    expect(sent['mode'], req['mode']);
    expect(sent['device_challenge'], matches(RegExp(r'^[0-9a-f]{64}$')));
    expect((req['device_challenge']! as String).length, 64);
    expect(sent['attempt'], attempt.id);
    expect(sent['attempt'], matches(RegExp(r'^[A-Za-z0-9_-]{1,64}$')));
  });

  test('redeem sends the fixture keys and completeNative accepts redeem_response', () async {
    final req = signinMap('redeem_request');
    final s = FakeServer({'POST /auth/signin/redeem': signinMap('redeem_response')});
    final store = InMemoryRefreshTokenStore();
    final tokens = InMemoryTokenStore();
    final g = OidcAuthGateway(api: s.api, tokens: tokens, refreshTokens: store);
    final attempt = SignInAttempt(id: 'att_1', deviceSecret: req['device_secret']! as String, deviceChallenge: SignInAttempt.challengeFor(req['device_secret']! as String));
    final session = await g.completeNative(attempt, req['code']! as String, deviceLabel: req['device_label']! as String);
    expect(s.seen.single.body, req);
    expect(session.userId, 'user-1');
    expect(session.capabilities, ['connections.manage']);
    expect(await store.load(), 'token-refresh');
    expect(tokens.token, 'token-access');
  });

  test('renewal sends the fixture fields and accepts refresh_response', () async {
    final req = signinMap('refresh_request_body');
    final s = FakeServer({'POST /auth/refresh': signinMap('refresh_response')});
    final store = InMemoryRefreshTokenStore(req['refresh_token']! as String);
    final g = OidcAuthGateway(api: s.api, tokens: InMemoryTokenStore(), refreshTokens: store);
    final session = await g.refreshSession();
    final sent = s.seen.single.body;
    expect(sent.keys.toSet(), req.keys.toSet());
    expect(sent['refresh_token'], req['refresh_token']);
    expect(sent['delivery'], req['delivery']);
    expect(sent['rotation_id'], isA<String>());
    expect(session!.refreshToken, 'token-refresh-2');
    expect(await store.load(), 'token-refresh-2');
  });

  test('error_envelope reads as a refusal with its code', () async {
    final env = signinMap('error_envelope');
    final s = FakeServer()..errors['POST /auth/signin/redeem'] = (403, env);
    final g = OidcAuthGateway(api: s.api, tokens: InMemoryTokenStore());
    final a = SignInAttempt.generate();
    await expectLater(
      g.completeNative(a, 'c'),
      throwsA(isA<AuthFailure>()
          .having((e) => e.code, 'code', 'not_invited')
          .having((e) => e.reason, 'reason', AuthFailureReason.notInvited)),
    );
    final api = SignInApi(s.api);
    await expectLater(api.redeem(a, 'c'), throwsA(isA<Forbidden>().having((e) => e.code, 'code', 'not_invited')));
    expect(const SignInLabels().messageFor('not_invited'), isNot(const SignInLabels().messageFor('unknown')));
  });

  test('providers_payload parses', () async {
    final s = FakeServer({'GET /auth/providers': signinMap('providers_payload')});
    final p = await SignInApi(s.api).providers();
    expect(p.signin.map((e) => e.id), ['google', 'microsoft']);
    expect(p.signin.first.label, 'Google');
    expect([p.breakGlass, p.defaultFlow], [false, 'signin']);
  });

  test('callback_redirects parse to the right return kinds', () {
    final r = signinMap('callback_redirects');
    Uri u(String k) => Uri.parse(r[k]! as String);
    expect(SignInReturn.parse(u('web_ok')).kind, SignInReturnKind.ok);
    final e = SignInReturn.parse(u('web_error'));
    expect([e.kind, e.reason], [SignInReturnKind.error, 'not_invited']);
    final n = SignInReturn.parse(u('native_return'));
    expect([n.kind, n.attempt, n.code], [SignInReturnKind.native, 'att_1', 'handoff-code']);
    final ne = SignInReturn.parse(u('native_error'));
    expect([ne.kind, ne.attempt, ne.reason, ne.code], [SignInReturnKind.native, 'att_1', 'not_invited', null]);
    final pending = SignInAttempt(id: 'att_1', deviceSecret: 's', deviceChallenge: SignInAttempt.challengeFor('s'));
    expect(n.matches(pending), isTrue);
    expect(SignInReturn.cleaned(u('web_ok')).toString(), 'https://app.example.org/done');
  });

  test('every code in labels_codes.json has its own message', () {
    final codes = ((signinMap('labels_codes')['codes']! as List).cast<String>());
    expect(codes, isNotEmpty);
    for (final c in codes) {
      expect(SignInLabels.codes, contains(c), reason: c);
      expect(SignInLabels.defaultMessages[c], isNotEmpty, reason: c);
    }
  });
}
