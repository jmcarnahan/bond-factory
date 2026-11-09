import 'package:bond_signin_ui/bond_signin_ui.dart';
import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/example_api.dart';
import 'package:sdk_demo/src/pages/auth_page.dart';

Finder byId(String id) => find.byWidgetPredicate((w) => w is Semantics && w.properties.identifier == id);

Map<String, Object?> answer(String token, {List<String> caps = const ['tasks.write', 'connections.manage']}) => {
      'token': token,
      'user': {'id': 'demo-user-1', 'email': 'demo@example.com', 'name': 'Demo User', 'capabilities': caps},
    };

Map<String, Object?> providers({bool breakGlass = false}) => {
      'signin': [
        {'id': 'fake-google', 'label': 'fake-google'},
        {'id': 'fake-microsoft', 'label': 'fake-microsoft'},
      ],
      'break_glass': breakGlass,
      'default_flow': 'signin',
    };

/// Records where the window was sent instead of leaving.
class _RecordingBrowser implements BrowserAuth {
  final List<Uri> urls = [];
  final List<Uri> callbacks = [];

  @override
  Future<Uri> run(Uri url, {required Uri callback, bool ephemeral = false}) async {
    urls.add(url);
    callbacks.add(callback);
    return callback;
  }
}

final home = Uri.parse('http://localhost:8078/auth');

Future<CannedHttpClient> pumpAuthPage(
  WidgetTester tester,
  CannedResponses responses, {
  Uri? url,
  Size size = const Size(1280, 800),
  List<Uri>? replaced,
  bool restore = false,
}) async {
  final http = CannedHttpClient(responses);
  DemoSession.reset(client: http, base: Uri.parse('http://test.invalid'));
  addTearDown(DemoSession.reset);
  setWideScreen(tester, size: size);
  await pumpApp(
    tester,
    AuthPage(currentUrl: url ?? home, replaceUrl: (replaced ?? <Uri>[]).add, restoreSession: restore),
  );
  return http;
}

Future<void> tapId(WidgetTester tester, String id) async {
  await tester.tap(byId(id));
  await tester.pump();
}

/// A signed-in page: the return said ok and the cookie session answers.
Future<CannedHttpClient> pumpSignedIn(WidgetTester tester, CannedResponses r, {Size? size}) async {
  r.json('GET', '/auth/providers', providers());
  final http = await pumpAuthPage(tester, r, url: Uri.parse('$home?signin=ok'), size: size ?? const Size(1280, 800));
  await pumpUntil(tester, byId('sdk.auth.user'));
  return http;
}

void main() {
  for (final size in [const Size(1280, 800), const Size(390, 844)]) {
    final lane = '${size.width.toInt()}x${size.height.toInt()}';

    testWidgets('signed out at $lane shows both provider buttons and no e-mail form', (tester) async {
      final r = CannedResponses()..json('GET', '/auth/providers', providers());
      await pumpAuthPage(tester, r, size: size);
      await pumpUntil(tester, byId('sdk.signin.fake-google'));

      expect(byId('sdk.signin.fake-microsoft'), findsOneWidget);
      expect(find.text('Continue with fake-google'), findsOneWidget);
      expect(find.text('Continue with fake-microsoft'), findsOneWidget);
      expect(byId('sdk.auth.signed-out'), findsOneWidget);
      expect(byId('sdk.auth.email'), findsNothing);
      expect(byId('sdk.signin.break-glass'), findsNothing);
      expect(byId('sdk.signin.error'), findsNothing);
      expect(tester.takeException(), isNull);
      await expectNoOverlays(tester);
    });

    testWidgets('signed in at $lane shows the claims and the actions', (tester) async {
      final r = CannedResponses()..json('POST', '/auth/refresh', answer('t-old111'));
      await pumpSignedIn(tester, r, size: size);

      for (final id in ['user', 'capabilities', 'token-tail', 'refresh', 'simulate-reuse', 'sign-out', 'renewals']) {
        expect(byId('sdk.auth.$id'), findsOneWidget, reason: 'sdk.auth.$id');
      }
      expect(find.text('Demo User (demo@example.com)'), findsOneWidget);
      expect(find.widgetWithText(Chip, 'connections.manage'), findsOneWidget);
      expect(byId('sdk.signin.fake-google'), findsNothing);
      expect(tester.takeException(), isNull);
      await expectNoOverlays(tester);
    });
  }

  testWidgets('a provider button asks the server for the start address and sends the window there', (tester) async {
    final browser = _RecordingBrowser();
    DemoSession.browserAuth = () => browser;
    addTearDown(() => DemoSession.browserAuth = defaultBrowserAuth);
    final r = CannedResponses()
      ..json('GET', '/auth/providers', providers())
      ..json('POST', '/auth/signin/fake-google/start', {'url': 'http://test.invalid/consent?state=abc'});
    final http = await pumpAuthPage(tester, r);
    await pumpUntil(tester, byId('sdk.signin.fake-google'));

    await tapId(tester, 'sdk.signin.fake-google');
    await pumpUntilThat(tester, () => browser.urls.isNotEmpty, what: 'navigation');

    expect(http.requestsTo('POST', '/auth/signin/fake-google/start').single.json,
        {'redirect_to': 'http://localhost:8078/auth', 'mode': 'web'});
    expect(browser.urls.single.path, '/consent');
    expect(browser.callbacks.single.toString(), 'http://localhost:8078/auth');
    await expectNoOverlays(tester);
  });

  testWidgets('a refused start shows the code inline', (tester) async {
    final r = CannedResponses()
      ..json('GET', '/auth/providers', providers())
      ..json('POST', '/auth/signin/fake-google/start',
          {'detail': {'code': 'invalid_origin', 'message': 'No'}}, status: 403);
    await pumpAuthPage(tester, r);
    await pumpUntil(tester, byId('sdk.signin.fake-google'));
    await tapId(tester, 'sdk.signin.fake-google');
    await pumpUntil(tester, byId('sdk.auth.error'));

    expect(find.text('No'), findsOneWidget);
    expect(find.bySemanticsLabel('No (invalid_origin)'), findsOneWidget);
    await expectNoOverlays(tester);
  });

  testWidgets('without break_glass there is no link and no e-mail form', (tester) async {
    final r = CannedResponses()..json('GET', '/auth/providers', providers());
    await pumpAuthPage(tester, r);
    await pumpUntil(tester, byId('sdk.signin.fake-google'));
    expect(byId('sdk.signin.break-glass'), findsNothing);
    expect(byId('sdk.auth.email'), findsNothing);
  });

  testWidgets('with break_glass the link appears and opens the form inline', (tester) async {
    final r = CannedResponses()..json('GET', '/auth/providers', providers(breakGlass: true));
    await pumpAuthPage(tester, r);
    await pumpUntil(tester, byId('sdk.signin.break-glass'));
    expect(byId('sdk.auth.email'), findsNothing);
    await tapId(tester, 'sdk.signin.break-glass');
    expect(byId('sdk.auth.email'), findsOneWidget);
    expect(byId('sdk.auth.sign-in'), findsOneWidget);
    await expectNoOverlays(tester);
  });

  testWidgets('the break-glass e-mail form signs in through the mock identity provider', (tester) async {
    final r = CannedResponses()
      ..json('GET', '/auth/providers', providers(breakGlass: true))
      ..json('POST', '/auth/firebase', answer('aaaa-abc123'));
    final http = await pumpAuthPage(tester, r);
    await pumpUntil(tester, byId('sdk.signin.break-glass'));
    await tapId(tester, 'sdk.signin.break-glass');
    await tapId(tester, 'sdk.auth.sign-in');
    await pumpUntil(tester, byId('sdk.auth.user'));

    expect(http.requestsTo('POST', '/auth/firebase').single.json, {'id_token': 'mock:demo@example.com'});
    expect(find.text('Token ends abc123'), findsOneWidget);
    await expectNoOverlays(tester);
  });

  testWidgets('break-glass refusal shows the message inline and keeps the code in the label', (tester) async {
    final r = CannedResponses()
      ..json('GET', '/auth/providers', providers(breakGlass: true))
      ..json('POST', '/auth/firebase',
          {'detail': {'code': 'not_invited', 'message': 'No invitation', 'hint': 'apple_relay'}}, status: 403);
    await pumpAuthPage(tester, r);
    await pumpUntil(tester, byId('sdk.signin.break-glass'));
    await tapId(tester, 'sdk.signin.break-glass');
    final handle = tester.ensureSemantics();
    await tapId(tester, 'sdk.auth.not-invited');
    await pumpUntil(tester, find.text('No invitation'));

    expect(find.textContaining('code:'), findsNothing);
    expect(find.textContaining('hint:'), findsNothing);
    expect(tester.getSemantics(byId('sdk.auth.error')).label, 'No invitation (not_invited; apple_relay)');
    expect(byId('sdk.auth.signed-out'), findsOneWidget);
    await expectNoOverlays(tester);
    handle.dispose();
  });

  testWidgets('a return with signin=error shows the inline strip with the label text and cleans the address',
      (tester) async {
    final replaced = <Uri>[];
    final r = CannedResponses()..json('GET', '/auth/providers', providers());
    await pumpAuthPage(tester, r,
        url: Uri.parse('$home?signin=error&reason=not_invited'), replaced: replaced);
    await pumpUntil(tester, byId('sdk.signin.error'));

    expect(find.text('This account has not been invited. Ask your administrator for access.'), findsOneWidget);
    expect(replaced.single.toString(), 'http://localhost:8078/auth');
    expect(byId('sdk.signin.fake-google'), findsOneWidget); // can try again
    await expectNoOverlays(tester);
  });

  testWidgets('a return with signin=ok completes the cookie session and cleans the address', (tester) async {
    final replaced = <Uri>[];
    final r = CannedResponses()
      ..json('POST', '/auth/refresh', answer('t-cookie1'))
      ..json('GET', '/auth/providers', providers());
    final http = await pumpAuthPage(tester, r, url: Uri.parse('$home?signin=ok'), replaced: replaced);
    await pumpUntil(tester, byId('sdk.auth.user'));

    expect(http.requestsTo('POST', '/auth/refresh').single.json, <String, Object?>{});
    expect(find.text('Token ends ookie1'), findsOneWidget);
    expect(replaced.single.toString(), 'http://localhost:8078/auth');
    await expectNoOverlays(tester);
  });

  testWidgets('a return with signin=ok the server cannot complete shows the refusal', (tester) async {
    final r = CannedResponses()
      ..json('POST', '/auth/refresh', {'detail': {'code': 'invalid_token', 'message': 'No'}}, status: 401)
      ..json('GET', '/auth/providers', providers());
    await pumpAuthPage(tester, r, url: Uri.parse('$home?signin=ok'));
    await pumpUntil(tester, byId('sdk.signin.error'));
    expect(byId('sdk.auth.user'), findsNothing);
    await expectNoOverlays(tester);
  });

  testWidgets('refresh renews through the gateway and shows Refreshed inline', (tester) async {
    final r = CannedResponses()
      ..json('POST', '/auth/refresh', answer('t-old111'))
      ..json('POST', '/auth/refresh', answer('t-new222'));
    final http = await pumpSignedIn(tester, r);

    await tapId(tester, 'sdk.auth.refresh');
    await pumpUntil(tester, find.text('Refreshed: token ends new222'));

    expect(find.text('Token ends new222'), findsOneWidget);
    expect(http.requestsTo('POST', '/auth/refresh'), hasLength(2));
    expect(byId('sdk.auth.error'), findsNothing);
    await expectNoOverlays(tester);
  });

  testWidgets('simulate reuse ends the session and shows the refresh_reused message inline', (tester) async {
    final r = CannedResponses()
      ..json('POST', '/auth/refresh', answer('t-old111'))
      ..json('POST', '/auth/refresh', {'detail': {'code': 'refresh_reused', 'message': 'Reused'}}, status: 401)
      ..json('POST', '/auth/simulate-reuse', {'detail': {'code': 'refresh_reused', 'message': 'Reused'}}, status: 401);
    final http = await pumpSignedIn(tester, r);

    await tapId(tester, 'sdk.auth.simulate-reuse');
    await pumpUntil(tester, byId('sdk.auth.ended'));

    expect(http.requestsTo('POST', '/auth/simulate-reuse'), hasLength(1));
    expect(find.textContaining('signed out because this session was used somewhere else'), findsOneWidget);
    expect(byId('sdk.auth.signed-out'), findsOneWidget);
    expect(byId('sdk.signin.fake-google'), findsOneWidget);
    expect(DemoSession.session, isNull);
    expect(DemoSession.tokens.token, isNull);
    await expectNoOverlays(tester);
  });

  testWidgets('endedReason renders sdk.auth.ended with the label text', (tester) async {
    final r = CannedResponses()..json('GET', '/auth/providers', providers());
    await pumpAuthPage(tester, r);
    await pumpUntil(tester, byId('sdk.signin.fake-google'));
    expect(byId('sdk.auth.ended'), findsNothing);

    DemoSession.endedReason.value = 'refresh_expired';
    await tester.pump();
    expect(byId('sdk.auth.ended'), findsOneWidget);
    expect(find.text('Your session expired. Sign in again.'), findsOneWidget);
    await expectNoOverlays(tester);
  });

  testWidgets('a forced 401 renews exactly once and the request then succeeds', (tester) async {
    final r = CannedResponses()
      ..json('POST', '/auth/refresh', answer('t-old111'))
      ..json('POST', '/auth/refresh', answer('t-new222'))
      ..json('GET', '/auth/me', {'detail': {'code': 'invalid_token', 'message': 'bad token'}}, status: 401)
      ..json('GET', '/auth/me', {'user': {'email': 'demo@example.com'}});
    final http = await pumpSignedIn(tester, r);

    expect(find.text('Renewals: 0'), findsOneWidget);
    await tapId(tester, 'sdk.auth.force-401');
    await pumpUntil(tester, find.text('1 renewal, request succeeded as demo@example.com'));

    expect(find.text('Renewals: 1'), findsOneWidget);
    expect(http.requestsTo('GET', '/auth/me').last.headers['Authorization'], 'Bearer t-new222');
    await expectNoOverlays(tester);
  });

  testWidgets('sign-out posts logout and returns to the sign-in screen', (tester) async {
    final r = CannedResponses()
      ..json('POST', '/auth/refresh', answer('t-old111'))
      ..json('POST', '/auth/logout', {'status': 'logged_out'});
    final http = await pumpSignedIn(tester, r);

    await tapId(tester, 'sdk.auth.sign-out');
    await pumpUntil(tester, byId('sdk.auth.signed-out'));

    expect(http.requestsTo('POST', '/auth/logout'), hasLength(1));
    expect(DemoSession.tokens.token, isNull);
    expect(byId('sdk.signin.fake-google'), findsOneWidget);
    expect(byId('sdk.auth.ended'), findsNothing);
    await expectNoOverlays(tester);
  });

  testWidgets('read-only values expose their text as a semantics label', (tester) async {
    final handle = tester.ensureSemantics();
    final r = CannedResponses()..json('POST', '/auth/refresh', answer('t-old111'));
    await pumpSignedIn(tester, r);

    const expected = {
      'sdk.auth.user': 'Demo User (demo@example.com)',
      'sdk.auth.capabilities': 'Capabilities: tasks.write, connections.manage',
      'sdk.auth.token-tail': 'Token ends old111',
      'sdk.auth.renewals': 'Renewals: 0',
    };
    final nodes = <String, String>{for (final id in expected.keys) id: tester.getSemantics(byId(id)).label};
    expect(nodes, expected);
    handle.dispose();
  });

  testWidgets('the error strip of a return is labelled for the walk', (tester) async {
    final handle = tester.ensureSemantics();
    final r = CannedResponses()..json('GET', '/auth/providers', providers());
    await pumpAuthPage(tester, r, url: Uri.parse('$home?signin=error&reason=not_invited'));
    await pumpUntil(tester, byId('sdk.signin.error'));
    expect(tester.getSemantics(byId('sdk.signin.error')).label, startsWith('This account has not been invited'));
    handle.dispose();
  });
}
