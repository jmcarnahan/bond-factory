import 'dart:async';

import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/example_api.dart';
import 'package:sdk_demo/src/pages/connections_page.dart';

Finder byId(String id) => find.byWidgetPredicate((w) => w is Semantics && w.properties.identifier == id);

Map<String, Object?> session({List<String> caps = const ['connections.manage']}) => {
      'token': 'sess-abc123',
      'user': {'id': 'demo-user-1', 'email': 'demo@example.com', 'name': 'Demo User', 'capabilities': caps},
    };

Map<String, Object?> row(String provider, {bool connected = false}) => {
      'provider': provider,
      'connected': connected,
      'email': connected ? 'demo@example.com' : null,
      'connected_at': connected ? '2026-11-08T17:04:05Z' : null,
      'needs_reconnect': false,
      'scopes': connected ? 'openid email' : '',
    };

Map<String, Object?> wantedSet({bool granted = false}) => {
      'id': 'mail_calendar',
      'provider': 'fake-google',
      'label': 'Mail and calendar',
      'scopes': ['mail.send', 'calendar'],
      'granted': granted,
    };

Map<String, Object?> listing(List<Map<String, Object?>> wanted) => {
      'connections': [row('fake-google'), row('fake-microsoft')],
      'wanted': wanted,
    };

final home = Uri.parse('http://localhost:8078/connections');

Future<CannedHttpClient> pump(
  WidgetTester t,
  CannedResponses r, {
  Size size = const Size(1280, 800),
  Uri? url,
  bool Function(Uri)? navigate,
}) async {
  final http = CannedHttpClient(r);
  DemoSession.reset(client: http, base: Uri.parse('http://test.invalid'));
  addTearDown(DemoSession.reset);
  setWideScreen(t, size: size);
  await pumpApp(t, ConnectionsPage(currentUrl: url ?? home, navigate: navigate, replaceUrl: (_) {}));
  await pumpUntil(t, byId('sdk.connections.list'));
  return http;
}

void main() {
  for (final size in [const Size(1280, 1400), const Size(390, 1600)]) {
    final lane = '${size.width.toInt()}x${size.height.toInt()}';

    testWidgets('a wanted set renders the ask card above the list at $lane', (t) async {
      final r = CannedResponses()
        ..json('POST', '/auth/demo', session())
        ..json('GET', '/connections', listing([wantedSet()]));
      await pump(t, r, size: size);

      expect(byId('sdk.scopes.ask-mail_calendar'), findsOneWidget);
      expect(find.text('Mail and calendar'), findsOneWidget);
      expect(find.text('Turn on access for your role'), findsOneWidget);
      expect(t.getTopLeft(byId('sdk.scopes.ask-mail_calendar')).dy,
          lessThan(t.getTopLeft(byId('sdk.connections.list')).dy));
      expect(t.takeException(), isNull);
      await expectNoOverlays(t);
    });
  }

  testWidgets('an empty wanted list renders no ask card', (t) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', session())
      ..json('GET', '/connections', listing(const []));
    await pump(t, r);
    expect(find.text('Turn on access for your role'), findsNothing);
    expect(find.byWidgetPredicate((w) => w is Semantics && (w.properties.identifier ?? '').startsWith('sdk.scopes.')),
        findsNothing);
    await expectNoOverlays(t);
  });

  testWidgets('a granted set is not asked again', (t) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', session())
      ..json('GET', '/connections', listing([wantedSet(granted: true)]));
    await pump(t, r);
    expect(byId('sdk.scopes.ask-mail_calendar'), findsNothing);
  });

  testWidgets('Allow starts the connect flow for the set and hands the address to the navigation', (t) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', session())
      ..json('GET', '/connections', listing([wantedSet()]))
      ..json('GET', '/connections/fake-google/start', {'url': 'http://test.invalid/consent?state=zz'});
    final sent = <Uri>[];
    final http = await pump(t, r, navigate: (u) {
      sent.add(u);
      return true;
    });
    await t.tap(byId('sdk.scopes.ask-mail_calendar'));
    await pumpUntilThat(t, () => sent.isNotEmpty, what: 'navigation');

    final start = http.requestsTo('GET', '/connections/fake-google/start').single;
    expect(start.url.queryParameters, {'redirect_to': 'http://localhost:8078/connections', 'set': 'mail_calendar'});
    expect(sent.single.path, '/consent');
    await expectNoOverlays(t);
  });

  testWidgets('a refused ask shows the code inline', (t) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', session())
      ..json('GET', '/connections', listing([wantedSet()]))
      ..json('GET', '/connections/fake-google/start', {'detail': {'code': 'unknown_set', 'message': 'No such set'}},
          status: 400);
    await pump(t, r, navigate: (_) => true);
    await t.tap(byId('sdk.scopes.ask-mail_calendar'));
    await pumpUntil(t, byId('sdk.connections.error'));
    expect(find.textContaining('code: unknown_set'), findsOneWidget);
    await expectNoOverlays(t);
  });

  testWidgets('after a declined return the set is still wanted and the reason shows inline', (t) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', session())
      ..json('GET', '/connections', listing([wantedSet()]));
    await pump(t, r, url: Uri.parse('$home?connection=error&provider=fake-google&reason=consent_declined'));
    expect(byId('sdk.connections.return'), findsOneWidget);
    expect(byId('sdk.scopes.ask-mail_calendar'), findsOneWidget);
    await expectNoOverlays(t);
  });

  testWidgets('a throwing navigation lands in the inline error strip and clears busy', (t) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', session())
      ..json('GET', '/connections', listing([wantedSet()]))
      ..json('GET', '/connections/fake-google/start', {'url': 'http://test.invalid/consent?state=zz'});
    await pump(t, r, navigate: (_) => throw StateError('no window'));
    await t.tap(byId('sdk.scopes.ask-mail_calendar'));
    await pumpUntil(t, byId('sdk.connections.error'));
    expect(find.textContaining('no window'), findsOneWidget);
    expect(byId('sdk.connections.connect-fake-google'), findsOneWidget);
    await expectNoOverlays(t);
  });

  testWidgets('a second tap while the ask runs starts nothing more', (t) async {
    final r = CannedResponses()
      ..json('POST', '/auth/demo', session())
      ..json('GET', '/connections', listing([wantedSet()]))
      ..json('GET', '/connections/fake-google/start', {'url': 'http://test.invalid/consent?state=zz'});
    final http = CannedHttpClient(r);
    DemoSession.reset(client: http, base: Uri.parse('http://test.invalid'));
    addTearDown(DemoSession.reset);
    setWideScreen(t, size: const Size(1280, 1400));
    // The first sign-in (page load) answers at once; the one inside the ask waits.
    final gate = Completer<void>();
    var calls = 0;
    final sent = <Uri>[];
    await pumpApp(
      t,
      ConnectionsPage(
        currentUrl: home,
        replaceUrl: (_) {},
        ensureSignedIn: () async {
          if (++calls == 1) return DemoSession.ensureSignedIn();
          await gate.future;
          return null;
        },
        navigate: (u) {
          sent.add(u);
          return true;
        },
      ),
    );
    await pumpUntil(t, byId('sdk.connections.list'));

    await t.tap(byId('sdk.scopes.ask-mail_calendar'));
    await t.tap(byId('sdk.scopes.ask-mail_calendar'), warnIfMissed: false);
    expect(calls, 2); // the second tap did not sign in again
    gate.complete();
    await pumpUntilThat(t, () => sent.isNotEmpty, what: 'navigation');
    expect(http.requestsTo('GET', '/connections/fake-google/start'), hasLength(1));
    expect(sent, hasLength(1));
  });
}
