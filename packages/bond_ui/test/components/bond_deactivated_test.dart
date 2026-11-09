import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/components/bond_deactivated.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'kit_host.dart';

void main() {
  testWidgets('shows words, note and extra inline; sign out fires', (t) async {
    setPhone(t);
    final handle = t.ensureSemantics();
    var out = 0;
    await pumpKit(
      t,
      BondDeactivated(
        title: 'Account off',
        body: 'Ask an admin.',
        note: '2 changes not sent',
        extra: const Text('extra control'),
        signOutLabel: 'Sign out',
        onSignOut: () => out++,
        signOutSemanticsId: 'deactivated.sign-out',
      ),
    );
    expect(find.text('Account off'), findsOneWidget);
    expect(find.text('2 changes not sent'), findsOneWidget);
    expect(find.text('extra control'), findsOneWidget);
    expect(byId('deactivated.sign-out'), findsOneWidget);
    await t.tap(find.text('Sign out'));
    expect(out, 1);
    await expectNoOverlays(t);
    expect(t.takeException(), isNull);
    handle.dispose();
  });
}
