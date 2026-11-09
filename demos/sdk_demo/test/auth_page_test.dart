import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/example_api.dart';
import 'package:sdk_demo/src/pages/auth_page.dart';

Map<String, Object?> answer(String token, {String id = 'demo-user-1', List<String> caps = const ['tasks.write', 'connections.manage']}) => {
      'token': token,
      'user': {'id': id, 'email': 'demo@example.com', 'name': 'Demo User', 'capabilities': caps},
    };

Future<CannedHttpClient> pumpAuthPage(WidgetTester tester, CannedResponses responses) async {
  final http = CannedHttpClient(responses);
  DemoSession.reset(client: http, base: Uri.parse('http://test.invalid'));
  addTearDown(DemoSession.reset);
  setWideScreen(tester, size: const Size(600, 2000));
  await pumpApp(tester, const AuthPage());
  return http;
}

Future<void> tap(WidgetTester tester, String label) async {
  await tester.tap(find.text(label));
  await tester.pump();
}

void main() {
  testWidgets('sign-in with the mock identity renders the user and capability chips', (tester) async {
    final r = CannedResponses()..json('POST', '/auth/firebase', answer('aaaa-abc123'));
    final http = await pumpAuthPage(tester, r);

    expect(find.text('Signed out'), findsOneWidget);
    await tap(tester, 'Sign in');
    await pumpUntil(tester, find.text('Demo User (demo@example.com)'));

    expect(http.requestsTo('POST', '/auth/firebase').single.json, {'id_token': 'mock:demo@example.com'});
    expect(find.widgetWithText(Chip, 'tasks.write'), findsOneWidget);
    expect(find.widgetWithText(Chip, 'connections.manage'), findsOneWidget);
    expect(find.text('Token ends abc123'), findsOneWidget);
    await expectNoOverlays(tester);
  });

  testWidgets('sign-in as the demo user posts the seeded user id', (tester) async {
    final r = CannedResponses()..json('POST', '/auth/demo', answer('t-demo01'));
    final http = await pumpAuthPage(tester, r);

    await tap(tester, 'Sign in as demo user');
    await pumpUntil(tester, find.text('Demo User (demo@example.com)'));

    expect(http.requestsTo('POST', '/auth/demo').single.json, {'user_id': 'demo-user-1'});
    await expectNoOverlays(tester);
  });

  testWidgets('not-invited shows code, message and hint inline', (tester) async {
    final r = CannedResponses()
      ..json(
        'POST',
        '/auth/firebase',
        {'detail': {'code': 'not_invited', 'message': 'No invitation for this address', 'hint': 'apple_relay'}},
        status: 403,
      );
    final http = await pumpAuthPage(tester, r);

    await tap(tester, 'Sign in as not-invited identity');
    await pumpUntil(tester, find.textContaining('code: not_invited'));

    expect(http.requestsTo('POST', '/auth/firebase').single.json, {'id_token': 'mock:notinvited@example.com'});
    expect(find.textContaining('message: No invitation for this address'), findsOneWidget);
    expect(find.textContaining('hint: apple_relay'), findsOneWidget);
    expect(find.text('Signed out'), findsOneWidget);
    await expectNoOverlays(tester);
  });

  testWidgets('an unreachable server shows a network error', (tester) async {
    final r = CannedResponses()..fail('POST', '/auth/firebase', Exception('down'));
    await pumpAuthPage(tester, r);

    await tap(tester, 'Sign in');
    await pumpUntil(tester, find.textContaining('code: network'));
    await expectNoOverlays(tester);
  });

  testWidgets('refresh renews the session and shows the new token tail', (tester) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', answer('t-old111'))
      ..json('POST', '/auth/demo', answer('t-new222'));
    final http = await pumpAuthPage(tester, r);

    await tap(tester, 'Sign in as demo user');
    await pumpUntil(tester, find.text('Refresh session'));
    await tap(tester, 'Refresh session');
    await pumpUntil(tester, find.text('Renewed: token ends new222'));

    expect(find.text('Token ends new222'), findsOneWidget);
    expect(http.requestsTo('POST', '/auth/demo'), hasLength(2));
    await expectNoOverlays(tester);
  });

  testWidgets('a forced 401 renews exactly once and the request then succeeds', (tester) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', answer('t-old111'))
      ..json('POST', '/auth/demo', answer('t-new222'))
      ..json('GET', '/auth/me', {'detail': {'code': 'invalid_token', 'message': 'bad token'}}, status: 401)
      ..json('GET', '/auth/me', {'user': {'email': 'demo@example.com'}});
    final http = await pumpAuthPage(tester, r);

    await tap(tester, 'Sign in as demo user');
    await pumpUntil(tester, find.text('Force a 401'));
    expect(find.text('Renewals: 0'), findsOneWidget);
    await tap(tester, 'Force a 401');
    await pumpUntil(tester, find.text('1 renewal, request succeeded as demo@example.com'));

    expect(find.text('Renewals: 1'), findsOneWidget);
    expect(http.requestsTo('GET', '/auth/me'), hasLength(2));
    expect(http.requestsTo('GET', '/auth/me').first.headers['Authorization'], 'Bearer broken.token.value');
    expect(http.requestsTo('GET', '/auth/me').last.headers['Authorization'], 'Bearer t-new222');
    expect(http.requestsTo('POST', '/auth/demo'), hasLength(2));
    await expectNoOverlays(tester);
  });

  testWidgets('every walkable element wears its sdk.auth identifier', (tester) async {
    final r = CannedResponses()..json('POST', '/auth/demo', answer('t-old111'));
    await pumpAuthPage(tester, r);
    await tap(tester, 'Sign in as demo user');
    await pumpUntil(tester, find.text('Sign out'));

    for (final id in [
      'email', 'sign-in', 'sign-in-demo', 'not-invited', 'user', 'capabilities', 'token-tail',
      'refresh', 'force-401', 'renewals', 'sign-out',
    ]) {
      expect(
        find.byWidgetPredicate((w) => w is Semantics && w.properties.identifier == 'sdk.auth.$id'),
        findsOneWidget,
        reason: 'sdk.auth.$id',
      );
    }
  });

  testWidgets('read-only values expose their text as a semantics label', (tester) async {
    final handle = tester.ensureSemantics();
    final r = CannedResponses()
      ..json('POST', '/auth/demo', answer('t-old111'))
      ..json('POST', '/auth/firebase', {'detail': {'code': 'not_invited', 'message': 'No'}}, status: 403);
    await pumpAuthPage(tester, r);

    expect(find.bySemanticsLabel('Signed out'), findsOneWidget);
    await tap(tester, 'Sign in as demo user');
    await pumpUntil(tester, find.text('Sign out'));
    for (final label in [
      'Demo User (demo@example.com)',
      'Capabilities: tasks.write, connections.manage',
      'Token ends old111',
      'Renewals: 0',
    ]) {
      expect(find.bySemanticsLabel(label), findsOneWidget, reason: label);
    }
    await tap(tester, 'Sign in as not-invited identity');
    await pumpUntil(tester, find.textContaining('code: not_invited'));
    expect(find.bySemanticsLabel(RegExp(r'^code: not_invited')), findsOneWidget);
    handle.dispose();
  });

  testWidgets('adjacent read-only ids each report only their own label', (tester) async {
    final handle = tester.ensureSemantics();
    final r = CannedResponses()..json('POST', '/auth/demo', answer('t-old111'));
    await pumpAuthPage(tester, r);
    await tap(tester, 'Sign in as demo user');
    await pumpUntil(tester, find.text('Sign out'));

    const expected = {
      'sdk.auth.user': 'Demo User (demo@example.com)',
      'sdk.auth.capabilities': 'Capabilities: tasks.write, connections.manage',
      'sdk.auth.token-tail': 'Token ends old111',
      'sdk.auth.renewals': 'Renewals: 0',
    };
    final nodes = <String, String>{
      for (final id in expected.keys)
        id: tester
            .getSemantics(find.byWidgetPredicate((w) => w is Semantics && w.properties.identifier == id))
            .label,
    };
    expect(nodes, expected);
    handle.dispose();
  });

  testWidgets('sign-out posts logout and returns to the signed-out view', (tester) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', answer('t-old111'))
      ..json('POST', '/auth/logout', {'status': 'logged_out'});
    final http = await pumpAuthPage(tester, r);

    await tap(tester, 'Sign in as demo user');
    await pumpUntil(tester, find.text('Sign out'));
    await tap(tester, 'Sign out');
    await pumpUntil(tester, find.text('Signed out'));

    expect(http.requestsTo('POST', '/auth/logout'), hasLength(1));
    expect(DemoSession.tokens.token, isNull);
    await expectNoOverlays(tester);
  });
}
