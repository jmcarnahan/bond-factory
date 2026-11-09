import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/components/bond_email_sign_in.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'kit_host.dart';

void main() {
  late List<(String, String)> signIns;
  late List<String> forgots;

  Future<void> pumpForm(WidgetTester t, {bool busy = false, String? error, String? notice}) {
    signIns = [];
    forgots = [];
    setPhone(t);
    return pumpKit(
      t,
      SingleChildScrollView(
        child: BondEmailSignIn(
          onSignIn: (e, p) => signIns.add((e, p)),
          onForgot: forgots.add,
          busy: busy,
          errorText: error,
          noticeText: notice,
        ),
      ),
    );
  }

  testWidgets('empty submit shows inline errors and calls nothing', (t) async {
    await pumpForm(t);
    await t.tap(find.byKey(const ValueKey('bond-login-submit')));
    await t.pump();
    expect(find.text('Enter your email.'), findsOneWidget);
    expect(find.text('Enter your password.'), findsOneWidget);
    expect(signIns, isEmpty);
    await expectNoOverlays(t);
  });

  testWidgets('malformed email is flagged, typing clears the message', (t) async {
    await pumpForm(t);
    await t.enterText(find.byKey(const ValueKey('bond-login-email')), 'not-an-email');
    await t.enterText(find.byKey(const ValueKey('bond-login-password')), 'pw');
    await t.tap(find.byKey(const ValueKey('bond-login-submit')));
    await t.pump();
    expect(find.text('Enter a valid email address.'), findsOneWidget);
    expect(signIns, isEmpty);
    await t.enterText(find.byKey(const ValueKey('bond-login-email')), 'a@example.com');
    await t.pump();
    expect(find.text('Enter a valid email address.'), findsNothing);
  });

  testWidgets('valid input calls onSignIn with the trimmed email', (t) async {
    await pumpForm(t);
    await t.enterText(find.byKey(const ValueKey('bond-login-email')), '  a@example.com ');
    await t.enterText(find.byKey(const ValueKey('bond-login-password')), 'secret');
    await t.tap(find.byKey(const ValueKey('bond-login-submit')));
    await t.pump();
    expect(signIns, [('a@example.com', 'secret')]);
  });

  testWidgets('forgot needs an email, then calls onForgot', (t) async {
    await pumpForm(t);
    await t.tap(find.byKey(const ValueKey('bond-login-forgot')));
    await t.pump();
    expect(find.text('Enter your email first, then ask for a reset.'), findsOneWidget);
    expect(forgots, isEmpty);
    await t.enterText(find.byKey(const ValueKey('bond-login-email')), 'a@example.com');
    await t.tap(find.byKey(const ValueKey('bond-login-forgot')));
    await t.pump();
    expect(forgots, ['a@example.com']);
  });

  testWidgets('page-supplied error and notice show inline; ids present', (t) async {
    final handle = t.ensureSemantics();
    await pumpForm(t, error: 'Wrong email or password.', notice: 'Reset email sent.');
    expect(find.text('Wrong email or password.'), findsOneWidget);
    expect(find.text('Reset email sent.'), findsOneWidget);
    expect(byId('login-submit'), findsOneWidget);
    expect(byId('login-email'), findsOneWidget);
    handle.dispose();
  });

  testWidgets('busy disables submit', (t) async {
    await pumpForm(t, busy: true);
    await t.tap(find.byKey(const ValueKey('bond-login-submit')), warnIfMissed: false);
    await t.pump();
    expect(signIns, isEmpty);
  });
}
