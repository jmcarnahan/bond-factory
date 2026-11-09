import 'package:bond_connections/bond_connections.dart';
import 'package:bond_connections_ui/bond_connections_ui.dart';
import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Finder byId(String id) => find.byWidgetPredicate((w) => w is Semantics && w.properties.identifier == id);

ConnectionStatus status({bool connected = false, bool needs = false}) => ConnectionStatus(
      provider: 'fake-google',
      connected: connected,
      needsReconnect: needs,
      email: connected ? 'demo@example.com' : null,
      connectedAt: connected ? DateTime.utc(2026, 11, 8, 17) : null,
    );

Future<void> pump(WidgetTester t, Widget child, {bool phone = true}) async {
  if (phone) setPhone(t);
  await pumpApp(t, SingleChildScrollView(child: Padding(padding: const EdgeInsets.all(16), child: child)),
      theme: BondTheme.build(BondTokens.fallback));
}

BondConnectionCard card(
  ConnectionStatus s, {
  List<String>? log,
  bool busy = false,
  String Function(DateTime)? fmt,
}) =>
    BondConnectionCard(
      status: s,
      semanticsId: 'sdk.connections',
      busy: busy,
      formatDate: fmt ?? (d) => 'DATE',
      onConnect: () => log?.add('connect'),
      onReconnect: () => log?.add('reconnect'),
      onDisconnect: () => log?.add('disconnect'),
    );

void main() {
  testWidgets('disconnected: only Connect, chip says not connected, no e-mail', (t) async {
    final log = <String>[];
    await pump(t, card(status(), log: log));
    expect(find.text('Not connected'), findsOneWidget);
    expect(find.text('Connect'), findsOneWidget);
    expect(find.text('Disconnect'), findsNothing);
    expect(find.text('Reconnect'), findsNothing);
    expect(find.textContaining('Connected as'), findsNothing);
    await t.tap(find.text('Connect'));
    expect(log, ['connect']);
    await expectNoOverlays(t);
  });

  testWidgets('connected: chip, e-mail, formatted date and only Disconnect', (t) async {
    await pump(t, card(status(connected: true)));
    expect(find.text('Connected'), findsOneWidget);
    expect(find.text('Connected as demo@example.com'), findsOneWidget);
    expect(find.text('Since DATE'), findsOneWidget);
    expect(find.text('Disconnect'), findsOneWidget);
    expect(find.text('Connect'), findsNothing);
    expect(find.text('Reconnect'), findsNothing);
  });

  testWidgets('needs reconnect: hint, Reconnect and Disconnect', (t) async {
    final log = <String>[];
    await pump(t, card(status(connected: true, needs: true), log: log));
    expect(find.text('Needs reconnect'), findsOneWidget);
    expect(find.textContaining('Connect again'), findsOneWidget);
    expect(find.text('Reconnect'), findsOneWidget);
    expect(find.text('Disconnect'), findsOneWidget);
    await t.tap(find.text('Reconnect'));
    expect(log, ['reconnect']);
  });

  testWidgets('disconnect is two steps: arm, then confirm', (t) async {
    final log = <String>[];
    await pump(t, card(status(connected: true), log: log));
    await t.tap(find.text('Disconnect'));
    await t.pump();
    expect(log, isEmpty);
    expect(byId('sdk.connections.disconnect-fake-google-confirm'), findsOneWidget);
    expect(byId('sdk.connections.disconnect-fake-google-cancel'), findsOneWidget);
    await t.tap(find.text('Disconnect')); // the confirm label
    await t.pump();
    expect(log, ['disconnect']);
    await expectNoOverlays(t);
  });

  testWidgets('cancel in the confirm step disconnects nothing', (t) async {
    final log = <String>[];
    await pump(t, card(status(connected: true), log: log));
    await t.tap(find.text('Disconnect'));
    await t.pump();
    await t.tap(find.text('Cancel'));
    await t.pump();
    expect(log, isEmpty);
    expect(find.text('Disconnect'), findsOneWidget);
  });

  testWidgets('ids: card, state chip and the button of the state', (t) async {
    await pump(t, card(status()));
    expect(byId('sdk.connections.card-fake-google'), findsOneWidget);
    expect(byId('sdk.connections.state-fake-google'), findsOneWidget);
    expect(byId('sdk.connections.connect-fake-google'), findsOneWidget);
    expect(byId('sdk.connections.reconnect-fake-google'), findsNothing);
  });

  testWidgets('busy waits: the button does not fire', (t) async {
    final log = <String>[];
    await pump(t, card(status(), log: log, busy: true));
    await t.tap(find.text('Connect'), warnIfMissed: false);
    expect(log, isEmpty);
  });

  testWidgets('a button without a callback is left out', (t) async {
    await pump(t, BondConnectionCard(status: status()));
    expect(find.text('Connect'), findsNothing);
    expect(find.text('Not connected'), findsOneWidget);
  });

  testWidgets('list: one card per provider, callbacks get the provider id, 390 px without overflow', (t) async {
    final log = <String>[];
    await pump(
      t,
      BondConnectionsList(
        statuses: [status(), const ConnectionStatus(provider: 'fake-microsoft')],
        labels: const ConnectionLabels(providerNames: {'fake-google': 'Fake Google', 'fake-microsoft': 'Fake Microsoft'}),
        onConnect: log.add,
        semanticsId: 'sdk.connections',
      ),
    );
    expect(find.text('Fake Google'), findsOneWidget);
    expect(find.text('Fake Microsoft'), findsOneWidget);
    await t.tap(byId('sdk.connections.connect-fake-microsoft'));
    expect(log, ['fake-microsoft']);
    expect(t.takeException(), isNull);
    await expectNoOverlays(t);
  });

  testWidgets('list: empty shows the empty state', (t) async {
    await pump(t, const BondConnectionsList(statuses: []));
    expect(find.text('No providers'), findsOneWidget);
  });

  testWidgets('return banner: connected is a notice, error carries the reason text', (t) async {
    await pump(
      t,
      const Column(children: [
        BondConnectionReturnBanner(ConnectionReturn(ConnectionOutcome.connected, provider: 'google'), semanticsId: 'a'),
        BondConnectionReturnBanner(
          ConnectionReturn(ConnectionOutcome.error, provider: 'google', reason: 'access_denied'),
          semanticsId: 'b',
        ),
      ]),
    );
    expect(find.text('google connected'), findsOneWidget);
    expect(find.text('Could not connect google'), findsOneWidget);
    expect(find.text('Access was declined.'), findsOneWidget);
    await expectNoOverlays(t);
  });

  testWidgets('return banner dismiss calls back', (t) async {
    var dismissed = 0;
    await pump(
      t,
      BondConnectionReturnBanner(
        const ConnectionReturn(ConnectionOutcome.connected),
        onDismiss: () => dismissed++,
        semanticsId: 'r',
      ),
    );
    await t.tap(byId('r-dismiss'));
    expect(dismissed, 1);
  });
}
