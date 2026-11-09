import 'package:bond_api/bond_api.dart';
import 'package:bond_auth/bond_auth.dart';
import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/example_api.dart';

Map<String, Object?> answer(String token) => {
      'token': token,
      'user': {'id': 'demo-user-1', 'email': 'demo@example.com', 'name': 'Demo User', 'capabilities': <String>[]},
    };

CannedHttpClient useCanned(CannedResponses r) {
  final http = CannedHttpClient(r);
  DemoSession.reset(client: http, base: Uri.parse('http://test.invalid'));
  addTearDown(DemoSession.reset);
  return http;
}

void main() {
  test('a refused identity does not take over renewal of the signed-in session', () async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', answer('t-one'))
      ..json('POST', '/auth/demo', answer('t-two'))
      ..json('POST', '/auth/firebase', {'detail': {'code': 'not_invited', 'message': 'No'}}, status: 403)
      ..json('GET', '/auth/me', {'detail': {'code': 'invalid_token', 'message': 'bad'}}, status: 401)
      ..json('GET', '/auth/me', {'user': {'email': 'demo@example.com'}});
    final http = useCanned(r);

    await DemoSession.ensureSignedIn();
    await expectLater(
      DemoSession.signInWithEmail(DemoSession.notInvitedEmail),
      throwsA(isA<AuthFailure>().having((e) => e.reason, 'reason', AuthFailureReason.notInvited)),
    );
    expect(DemoSession.session, isNotNull);
    expect(DemoSession.tokens.token, 't-one');

    DemoSession.tokens.token = 'broken.token.value';
    final me = await DemoSession.api.getJson('/auth/me');

    expect(me['user'], isNotNull);
    expect(DemoSession.renewals.value, 1);
    expect(http.requestsTo('POST', '/auth/demo'), hasLength(2));
    expect(http.requestsTo('POST', '/auth/refresh'), isEmpty);
    expect(DemoSession.tokens.token, 't-two');
  });

  test('a rejected renewal clears the session and ensureSignedIn signs in afresh', () async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', answer('t-one'))
      ..json('POST', '/auth/demo', {'detail': {'code': 'deactivated', 'message': 'off'}}, status: 403)
      ..json('POST', '/auth/demo', answer('t-three'))
      ..json('GET', '/auth/me', {'detail': {'code': 'invalid_token', 'message': 'bad'}}, status: 401);
    final http = useCanned(r);

    await DemoSession.ensureSignedIn();
    DemoSession.tokens.token = 'broken.token.value';
    await expectLater(DemoSession.api.getJson('/auth/me'), throwsA(isA<Unauthorized>()));

    expect(DemoSession.tokens.token, isNull);
    expect(DemoSession.session, isNull);

    final s = await DemoSession.ensureSignedIn();
    expect(s.token, 't-three');
    expect(DemoSession.tokens.token, 't-three');
    expect(http.requestsTo('POST', '/auth/demo'), hasLength(3));
  });

  test('a cookie session that ended is not answered by a demo sign-in', () async {
    final r = CannedResponses()
      ..json('POST', '/auth/refresh', {'detail': {'code': 'refresh_revoked', 'message': 'Gone'}}, status: 401)
      ..json('POST', '/auth/demo', answer('t-demo'));
    final http = useCanned(r);
    DemoSession.useCookieSession = true;

    await expectLater(DemoSession.ensureSignedIn(), throwsA(isA<AuthFailure>()));

    expect(DemoSession.endedReason.value, 'refresh_revoked');
    expect(http.requestsTo('POST', '/auth/demo'), isEmpty);
    expect(DemoSession.session, isNull);
  });

  test('no cookie session falls back to the demo sign-in', () async {
    final r = CannedResponses()
      ..json('POST', '/auth/refresh', {'detail': {'code': 'invalid_token', 'message': 'None'}}, status: 401)
      ..json('POST', '/auth/demo', answer('t-demo'));
    final http = useCanned(r);
    DemoSession.useCookieSession = true;

    final s = await DemoSession.ensureSignedIn();

    expect(s.token, 't-demo');
    expect(http.requestsTo('POST', '/auth/demo'), hasLength(1));
    expect(DemoSession.endedReason.value, isNull);
  });
}
