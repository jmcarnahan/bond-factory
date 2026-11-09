import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/example_api.dart';
import 'package:sdk_demo/src/pages/connections_page.dart';

Finder byId(String id) => find.byWidgetPredicate((w) => w is Semantics && w.properties.identifier == id);

String textOf(WidgetTester t, String id) {
  final texts = find.descendant(of: byId(id), matching: find.byType(Text));
  if (texts.evaluate().isNotEmpty) return t.widget<Text>(texts.first).data!;
  return t.widget<SelectableText>(find.descendant(of: byId(id), matching: find.byType(SelectableText))).data!;
}

Map<String, Object?> session({List<String> caps = const ['connections.manage']}) => {
      'token': 'sess-abc123',
      'user': {'id': 'demo-user-1', 'email': 'demo@example.com', 'name': 'Demo User', 'capabilities': caps},
    };

Map<String, Object?> row(String provider, {bool connected = false, bool needs = false}) => {
      'provider': provider,
      'connected': connected,
      'email': connected ? 'demo@example.com' : null,
      'connected_at': connected ? '2026-11-08T17:04:05Z' : null,
      'needs_reconnect': needs,
      'scopes': connected ? 'openid email' : '',
    };

final home = Uri.parse('http://localhost:8078/connections');

Future<CannedHttpClient> pumpPage(
  WidgetTester t,
  CannedResponses r, {
  Uri? url,
  bool Function(Uri)? navigate,
  void Function(Uri)? replaceUrl,
}) async {
  final http = CannedHttpClient(r);
  DemoSession.reset(client: http, base: Uri.parse('http://test.invalid'));
  addTearDown(DemoSession.reset);
  setWideScreen(t, size: const Size(600, 2600));
  await pumpApp(t, ConnectionsPage(currentUrl: url ?? home, navigate: navigate, replaceUrl: replaceUrl ?? (_) {}));
  await pumpUntil(t, byId('sdk.connections.list'));
  return http;
}

CannedResponses twoProviders() => CannedResponses()
  ..json('POST', '/auth/demo', session())
  ..json('GET', '/connections', [row('fake-google'), row('fake-microsoft')]);

void main() {
  testWidgets('lists both fake providers, signed in first, each with Connect', (t) async {
    final http = await pumpPage(t, twoProviders());
    expect(http.requestsTo('POST', '/auth/demo'), hasLength(1));
    expect(http.requestsTo('GET', '/connections').single.headers['Authorization'], 'Bearer sess-abc123');
    expect(byId('sdk.connections.card-fake-google'), findsOneWidget);
    expect(byId('sdk.connections.card-fake-microsoft'), findsOneWidget);
    expect(byId('sdk.connections.connect-fake-google'), findsOneWidget);
    expect(byId('sdk.connections.connect-fake-microsoft'), findsOneWidget);
    expect(find.text('Not connected'), findsNWidgets(2));
    expect(byId('sdk.connections.return'), findsNothing);
    await expectNoOverlays(t);
  });

  testWidgets('connect asks for the start address with this origin and shows it off the web', (t) async {
    final r = twoProviders()
      ..json('GET', '/connections/fake-google/start', {'url': 'http://test.invalid/connections/fake-google/go?state=abc'});
    final http = await pumpPage(t, r);
    await t.tap(byId('sdk.connections.connect-fake-google'));
    await pumpUntil(t, byId('sdk.connections.start-url'));

    final start = http.requestsTo('GET', '/connections/fake-google/start').single;
    expect(start.url.queryParameters, {'redirect_to': 'http://localhost:8078/connections'});
    expect(start.headers['Authorization'], 'Bearer sess-abc123');
    expect(textOf(t, 'sdk.connections.start-url'), contains('/connections/fake-google/go?state=abc'));
  });

  testWidgets('connect hands the address to the navigation and shows nothing', (t) async {
    final r = twoProviders()
      ..json('GET', '/connections/fake-google/start', {'url': 'http://test.invalid/connections/fake-google/go?state=abc'});
    final sent = <Uri>[];
    await pumpPage(t, r, navigate: (u) {
      sent.add(u);
      return true;
    });
    await t.tap(byId('sdk.connections.connect-fake-google'));
    await pumpUntilThat(t, () => sent.isNotEmpty, what: 'navigation');
    expect(sent.single.path, '/connections/fake-google/go');
    expect(byId('sdk.connections.start-url'), findsNothing);
  });

  testWidgets('simulate expiry shows the needs-reconnect chip and Reconnect', (t) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', session())
      ..json('GET', '/connections', [row('fake-google', connected: true), row('fake-microsoft')])
      ..json('GET', '/connections', [row('fake-google', connected: true, needs: true), row('fake-microsoft')])
      ..json('POST', '/connections/fake-google/simulate-expiry', row('fake-google', connected: true, needs: true));
    final http = await pumpPage(t, r);
    expect(find.text('Connected'), findsOneWidget);
    await t.tap(byId('sdk.connections.simulate-expiry-fake-google'));
    await pumpUntil(t, find.text('Needs reconnect'));
    expect(http.requestsTo('POST', '/connections/fake-google/simulate-expiry'), hasLength(1));
    expect(byId('sdk.connections.reconnect-fake-google'), findsOneWidget);
    expect(byId('sdk.connections.simulate-expiry-fake-google'), findsNothing);
    await expectNoOverlays(t);
  });

  testWidgets('disconnect is two steps and the list is read again afterwards', (t) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', session())
      ..json('GET', '/connections', [row('fake-google', connected: true), row('fake-microsoft')])
      ..json('GET', '/connections', [row('fake-google'), row('fake-microsoft')])
      ..json('DELETE', '/connections/fake-google', row('fake-google'));
    final http = await pumpPage(t, r);
    await t.tap(byId('sdk.connections.disconnect-fake-google'));
    await t.pump();
    expect(http.requestsTo('DELETE', '/connections/fake-google'), isEmpty);
    expect(byId('sdk.connections.disconnect-fake-google-confirm'), findsOneWidget);
    await t.tap(byId('sdk.connections.disconnect-fake-google-confirm'));
    await pumpUntil(t, byId('sdk.connections.connect-fake-google'));
    expect(http.requestsTo('DELETE', '/connections/fake-google'), hasLength(1));
    expect(http.requestsTo('GET', '/connections'), hasLength(2));
    expect(find.text('Not connected'), findsNWidgets(2));
  });

  testWidgets('a return URL with connection=connected shows the banner above live state', (t) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', session())
      ..json('GET', '/connections', [row('fake-google', connected: true), row('fake-microsoft')]);
    await pumpPage(t, r, url: Uri.parse('http://localhost:8078/connections?connection=connected&provider=fake-google'));
    expect(byId('sdk.connections.return'), findsOneWidget);
    expect(find.text('Fake Google connected'), findsOneWidget);
    expect(find.text('Connected as demo@example.com'), findsOneWidget);
    await t.tap(byId('sdk.connections.return-dismiss'));
    await t.pump();
    expect(byId('sdk.connections.return'), findsNothing);
  });

  testWidgets('a return URL with an error shows the reason in words', (t) async {
    await pumpPage(t, twoProviders(),
        url: Uri.parse('http://localhost:8078/connections?connection=error&provider=fake-google&reason=access_denied'));
    expect(find.text('Could not connect Fake Google'), findsOneWidget);
    expect(find.text('Access was declined.'), findsOneWidget);
  });

  testWidgets('Reconnect starts the flow again for the same provider', (t) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', session())
      ..json('GET', '/connections', [row('fake-google', connected: true, needs: true), row('fake-microsoft')])
      ..json('GET', '/connections/fake-google/start', {'url': 'http://test.invalid/connections/fake-google/go?state=zz'});
    final sent = <Uri>[];
    final http = await pumpPage(t, r, navigate: (u) {
      sent.add(u);
      return true;
    });
    await t.tap(byId('sdk.connections.reconnect-fake-google'));
    await pumpUntilThat(t, () => sent.isNotEmpty, what: 'navigation');
    expect(http.requestsTo('GET', '/connections/fake-google/start'), hasLength(1));
    expect(http.requestsTo('GET', '/connections/fake-microsoft/start'), isEmpty);
    expect(sent.single.queryParameters['state'], 'zz');
  });

  testWidgets('a refused start shows the server code inline and navigates nowhere', (t) async {
    final r = twoProviders()
      ..json('GET', '/connections/fake-google/start',
          {'detail': {'code': 'redirect_not_allowed', 'message': 'That redirect address is not allowed.'}},
          status: 400);
    final sent = <Uri>[];
    await pumpPage(t, r, navigate: (u) {
      sent.add(u);
      return true;
    });
    await t.tap(byId('sdk.connections.connect-fake-google'));
    await pumpUntil(t, byId('sdk.connections.error'));
    expect(
      textOf(t, 'sdk.connections.error'),
      'code: redirect_not_allowed | message: That redirect address is not allowed.',
    );
    expect(sent, isEmpty);
    expect(byId('sdk.connections.start-url'), findsNothing);
    expect(byId('sdk.connections.connect-fake-google'), findsOneWidget); // can try again
  });

  testWidgets('dismissing the return banner leaves the address alone (documented, not cleaned)', (t) async {
    final sent = <Uri>[];
    await pumpPage(t, twoProviders(),
        url: Uri.parse('http://localhost:8078/connections?connection=connected&provider=fake-google'),
        navigate: (u) {
      sent.add(u);
      return true;
    });
    await t.tap(byId('sdk.connections.return-dismiss'));
    await t.pump();
    expect(byId('sdk.connections.return'), findsNothing);
    expect(sent, isEmpty);
  });

  testWidgets('a forged connected URL over a disconnected list shows no positive banner', (t) async {
    final replaced = <Uri>[];
    await pumpPage(t, twoProviders(),
        url: Uri.parse('http://localhost:8078/connections?connection=connected&provider=fake-google'),
        replaceUrl: replaced.add);
    expect(find.text('Fake Google connected'), findsNothing);
    expect(find.text('Could not connect Fake Google'), findsOneWidget);
    expect(find.text('Nothing changed: this provider is not connected.'), findsOneWidget);
    expect(find.text('Not connected'), findsNWidgets(2));
    expect(replaced.single.toString(), 'http://localhost:8078/connections');
  });

  testWidgets('a confirmed return also cleans the address, once, and a disconnect does not bring the banner back',
      (t) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', session())
      ..json('GET', '/connections', [row('fake-google', connected: true), row('fake-microsoft')])
      ..json('GET', '/connections', [row('fake-google'), row('fake-microsoft')])
      ..json('DELETE', '/connections/fake-google', row('fake-google'));
    final replaced = <Uri>[];
    await pumpPage(t, r,
        url: Uri.parse('http://localhost:8078/connections?connection=connected&provider=fake-google&keep=1'),
        replaceUrl: replaced.add);
    expect(find.text('Fake Google connected'), findsOneWidget);
    expect(replaced.single.toString(), 'http://localhost:8078/connections?keep=1');
    await t.tap(byId('sdk.connections.return-dismiss'));
    await t.pump();
    await t.tap(byId('sdk.connections.disconnect-fake-google'));
    await t.pump();
    await t.tap(byId('sdk.connections.disconnect-fake-google-confirm'));
    await pumpUntil(t, byId('sdk.connections.connect-fake-google'));
    expect(byId('sdk.connections.return'), findsNothing);
    expect(replaced, hasLength(1));
  });

  testWidgets('an ordinary visit leaves the address alone', (t) async {
    final replaced = <Uri>[];
    await pumpPage(t, twoProviders(), replaceUrl: replaced.add);
    expect(replaced, isEmpty);
    expect(byId('sdk.connections.return'), findsNothing);
  });

  testWidgets('a session without connections.manage sees the list and a note, but no actions', (t) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', session(caps: const []))
      ..json('GET', '/connections', [row('fake-google', connected: true), row('fake-microsoft', connected: true, needs: true)]);
    final http = await pumpPage(t, r);
    expect(byId('sdk.connections.no-manage'), findsOneWidget);
    expect(byId('sdk.connections.card-fake-google'), findsOneWidget);
    expect(find.text('Connected'), findsOneWidget);
    expect(find.text('Needs reconnect'), findsOneWidget);
    for (final p in ['fake-google', 'fake-microsoft']) {
      expect(byId('sdk.connections.connect-$p'), findsNothing);
      expect(byId('sdk.connections.reconnect-$p'), findsNothing);
      expect(byId('sdk.connections.disconnect-$p'), findsNothing);
      expect(byId('sdk.connections.simulate-expiry-$p'), findsNothing);
    }
    expect(http.requestsTo('GET', '/connections/fake-google/start'), isEmpty);
    await expectNoOverlays(t);
  });

  testWidgets('the text nodes of the page expose their text as the semantics label', (t) async {
    final handle = t.ensureSemantics();
    final r = CannedResponses()
      ..json('POST', '/auth/demo', session(caps: const []))
      ..json('GET', '/connections', [row('fake-google', connected: true)])
      ..json('GET', '/connections/fake-google/start', {'detail': {'code': 'forbidden', 'message': 'No.'}}, status: 403);
    await pumpPage(t, r);
    expect(t.getSemantics(byId('sdk.connections.no-manage')).label, startsWith('This account cannot change'));
    expect(t.getSemantics(byId('sdk.connections.state-fake-google')).label, 'Connected');
    handle.dispose();
  });

  testWidgets('an error line and a start address are labelled too', (t) async {
    final handle = t.ensureSemantics();
    final r = twoProviders()
      ..json('GET', '/connections/fake-google/start', {'url': 'http://test.invalid/connections/fake-google/go?state=abc'})
      ..json('GET', '/connections/fake-microsoft/start', {'detail': {'code': 'unknown_provider', 'message': 'No.'}}, status: 404);
    await pumpPage(t, r);
    await t.tap(byId('sdk.connections.connect-fake-google'));
    await pumpUntil(t, byId('sdk.connections.start-url'));
    expect(t.getSemantics(byId('sdk.connections.start-url')).label, contains('/go?state=abc'));
    await t.tap(byId('sdk.connections.connect-fake-microsoft'));
    await pumpUntil(t, byId('sdk.connections.error'));
    expect(t.getSemantics(byId('sdk.connections.error')).label, 'code: unknown_provider | message: No.');
    handle.dispose();
  });

  testWidgets('a manager sees no note', (t) async {
    await pumpPage(t, twoProviders());
    expect(byId('sdk.connections.no-manage'), findsNothing);
  });

  testWidgets('a server refusal shows its code inline', (t) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', session())
      ..json('GET', '/connections', {'detail': {'code': 'db_unavailable', 'message': 'Try later'}}, status: 503);
    final http = CannedHttpClient(r);
    DemoSession.reset(client: http, base: Uri.parse('http://test.invalid'));
    addTearDown(DemoSession.reset);
    await pumpApp(t, ConnectionsPage(currentUrl: home));
    await pumpUntil(t, byId('sdk.connections.error'));
    expect(textOf(t, 'sdk.connections.error'), 'code: db_unavailable | message: Try later');
    expect(byId('sdk.connections.list'), findsNothing);
  });
}
