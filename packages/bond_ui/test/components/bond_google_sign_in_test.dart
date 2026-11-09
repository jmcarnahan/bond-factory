import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/components/bond_google_sign_in.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'kit_host.dart';

void main() {
  testWidgets('button calls back, notice shows inline, ids present', (t) async {
    setPhone(t);
    final handle = t.ensureSemantics();
    var taps = 0;
    await pumpKit(
      t,
      BondGoogleSignInButton(label: 'Continue with Google', onPressed: () => taps++, notice: 'Not configured'),
    );
    expect(byId('google-sign-in'), findsOneWidget);
    expect(byId('google-sign-in-notice'), findsOneWidget);
    expect(find.text('Not configured'), findsOneWidget);
    await t.tap(find.text('Continue with Google'));
    expect(taps, 1);
    await expectNoOverlays(t);
    handle.dispose();
  });

  testWidgets('disabled with no callback', (t) async {
    await pumpKit(t, const BondGoogleSignInButton(label: 'Go', onPressed: null));
    final ink = t.widget<InkWell>(find.byType(InkWell));
    expect(ink.onTap, isNull);
    expect(find.byType(CustomPaint), findsWidgets);
  });
}
