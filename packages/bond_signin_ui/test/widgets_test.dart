import 'dart:convert';
import 'dart:io';

import 'package:bond_auth/bond_auth.dart';
import 'package:bond_connections/bond_connections.dart';
import 'package:bond_signin_ui/bond_signin_ui.dart';
import 'package:bond_signin/bond_signin.dart';
import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const _labels = SignInLabels();

AuthProviders _providers({bool breakGlass = false}) => AuthProviders(
      signin: const [SignInProvider(id: 'google', label: 'Google'), SignInProvider(id: 'microsoft', label: 'Microsoft')],
      breakGlass: breakGlass,
    );

Finder _id(String id) => find.byWidgetPredicate((w) => w is Semantics && w.properties.identifier == id, description: 'semantics $id');

Future<void> _sizes(WidgetTester t, Future<void> Function() body) async {
  for (final phone in [false, true]) {
    if (phone) {
      setPhone(t);
    } else {
      setWideScreen(t);
    }
    await body();
  }
}

void main() {
  group('BondSignInScreen', () {
    testWidgets('one button per provider with ids, invite-only line, no overlays', (t) async {
      await _sizes(t, () async {
        final started = <String>[];
        await pumpApp(t, BondSignInScreen(providers: _providers(), labels: _labels, onStart: (id) async => started.add(id)));
        expect(_id('sdk.signin.google'), findsOneWidget);
        expect(_id('sdk.signin.microsoft'), findsOneWidget);
        expect(find.text('Continue with Google'), findsOneWidget);
        expect(find.text(_labels.inviteOnly), findsOneWidget);
        expect(_id('sdk.signin.error'), findsNothing);
        await t.tap(find.text('Continue with Microsoft'));
        await t.pump();
        expect(started.last, 'microsoft');
        await expectNoOverlays(t);
      });
    });

    testWidgets('error strip maps two codes through the labels', (t) async {
      await _sizes(t, () async {
        for (final code in ['not_invited', 'refresh_reused']) {
          await pumpApp(t, BondSignInScreen(providers: _providers(), labels: _labels, onStart: (_) async {}, errorCode: code));
          expect(_id('sdk.signin.error'), findsOneWidget);
          expect(find.text(_labels.messageFor(code)), findsOneWidget);
          await expectNoOverlays(t);
        }
        expect(_labels.messageFor('not_invited'), isNot(_labels.messageFor('refresh_reused')));
      });
    });

    testWidgets('an unknown code reads as the unknown message', (t) async {
      setPhone(t);
      await pumpApp(t, BondSignInScreen(providers: _providers(), labels: _labels, onStart: (_) async {}, errorCode: 'weird'));
      expect(find.text(_labels.messageFor('unknown')), findsOneWidget);
    });

    testWidgets('busy disables the buttons and says so', (t) async {
      setPhone(t);
      var started = 0;
      await pumpApp(t, BondSignInScreen(providers: _providers(), labels: _labels, onStart: (_) async => started++, busy: true));
      expect(find.text(_labels.working), findsOneWidget);
      await t.tap(find.text('Continue with Google'), warnIfMissed: false);
      await t.pump();
      expect(started, 0);
    });

    testWidgets('break-glass link is hidden unless the server allows it and the app supplies one', (t) async {
      setWideScreen(t);
      Widget form(BuildContext c) => const Text('admin form');
      await pumpApp(t, BondSignInScreen(providers: _providers(), labels: _labels, onStart: (_) async {}, breakGlass: form));
      expect(_id('sdk.signin.break-glass'), findsNothing); // server says no
      await pumpApp(t, BondSignInScreen(providers: _providers(breakGlass: true), labels: _labels, onStart: (_) async {}));
      expect(_id('sdk.signin.break-glass'), findsNothing); // app supplied nothing
    });

    testWidgets('break-glass toggles the builder inline, no route and no overlay', (t) async {
      await _sizes(t, () async {
        Widget form(BuildContext c) => const Text('admin form');
        await pumpApp(t, BondSignInScreen(providers: _providers(breakGlass: true), labels: _labels, onStart: (_) async {}, breakGlass: form));
        expect(_id('sdk.signin.break-glass'), findsOneWidget);
        expect(find.text('admin form'), findsNothing);
        await t.tap(find.text(_labels.breakGlass));
        await t.pump();
        expect(find.text('admin form'), findsOneWidget);
        await expectNoOverlays(t);
        await t.tap(find.text(_labels.breakGlass));
        await t.pump();
        expect(find.text('admin form'), findsNothing);
      });
    });

    testWidgets('a custom prefix changes the ids', (t) async {
      setPhone(t);
      await pumpApp(t, BondSignInScreen(providers: _providers(), labels: _labels, onStart: (_) async {}, errorCode: 'deactivated', semanticsPrefix: 'app.login'));
      expect(_id('app.login.google'), findsOneWidget);
      expect(_id('app.login.error'), findsOneWidget);
      expect(_id('sdk.signin.google'), findsNothing);
    });
  });

  group('BondScopeAskCard', () {
    const wanted = [
      WantedSet(id: 'mail_send', provider: 'google', label: 'Send mail', granted: false),
      WantedSet(id: 'calendar', provider: 'google', label: 'Calendar', granted: true),
      WantedSet(id: 'contacts', provider: 'google', label: 'Contacts', granted: false),
    ];

    testWidgets('renders only ungranted sets and asks for the tapped one', (t) async {
      await _sizes(t, () async {
        final asked = <String>[];
        await pumpApp(t, BondScopeAskCard(wanted: wanted, labels: _labels, onAsk: (s) async => asked.add(s.id)));
        expect(find.text('Send mail'), findsOneWidget);
        expect(find.text('Contacts'), findsOneWidget);
        expect(find.text('Calendar'), findsNothing);
        expect(_id('sdk.scopes.ask-mail_send'), findsOneWidget);
        expect(_id('sdk.scopes.ask-contacts'), findsOneWidget);
        expect(_id('sdk.scopes.ask-calendar'), findsNothing);
        await t.tap(find.text(_labels.allow).first);
        await t.pump();
        expect(asked, ['mail_send']);
        await expectNoOverlays(t);
      });
    });

    testWidgets('renders nothing when all are granted or none are wanted', (t) async {
      setPhone(t);
      await pumpApp(t, BondScopeAskCard(wanted: const [WantedSet(id: 'a', provider: 'google', label: 'A', granted: true)], labels: _labels, onAsk: (_) async {}));
      expect(find.text(_labels.scopesTitle), findsNothing);
      expect(find.byType(BondButton), findsNothing);
      await pumpApp(t, BondScopeAskCard(wanted: const [], labels: _labels, onAsk: (_) async {}));
      expect(find.text(_labels.scopesTitle), findsNothing);
    });

    testWidgets('disables the rows while an ask runs', (t) async {
      setPhone(t);
      var calls = 0;
      await pumpApp(t, BondScopeAskCard(wanted: wanted, labels: _labels, onAsk: (_) {
        calls++;
        return Future<void>.delayed(const Duration(seconds: 1));
      }));
      await t.tap(find.byType(BondButton).first);
      await t.pump();
      await t.tap(find.byType(BondButton).last, warnIfMissed: false);
      await t.pump();
      expect(calls, 1);
      await t.pump(const Duration(seconds: 2));
    });

    testWidgets('a failing ask shows an inline error and does not escape', (t) async {
      setPhone(t);
      await pumpApp(t, BondScopeAskCard(wanted: wanted, labels: _labels, onAsk: (_) async => throw StateError('boom')));
      await t.tap(find.text(_labels.allow).first);
      await t.pump();
      expect(find.text(_labels.messageFor('unknown')), findsOneWidget);
      expect(_id('sdk.scopes.error'), findsOneWidget);
      await expectNoOverlays(t);
    });
  });

  test('wanted_list.json fixture reads as WantedSet and drives the card', () {
    final raw = jsonDecode(File('../../fixtures/signin/wanted_list.json').readAsStringSync());
    final list = ConnectionList.fromJson({'connections': <Object?>[], 'wanted': raw});
    expect(list.wanted.single.id, 'mail');
    expect([list.wanted.single.provider, list.wanted.single.granted], ['google', false]);
    expect(list.wanted.single.scopes, hasLength(1));
  });
}
