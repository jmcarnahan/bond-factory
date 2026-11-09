import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/shell/bond_account_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../components/kit_host.dart';

void main() {
  testWidgets('toggle expands actions in place, initials by default', (t) async {
    setPhone(t);
    final handle = t.ensureSemantics();
    var expanded = false;
    var signOuts = 0;
    await pumpKit(
      t,
      StatefulBuilder(
        builder: (context, set) => BondAccountCard(
          name: 'Alex Rivera',
          subtitle: 'Admin',
          expanded: expanded,
          onToggle: () => set(() => expanded = !expanded),
          semanticsId: 'account',
          actions: [BondAccountRow(icon: Icons.logout, label: 'Sign out', onTap: () => signOuts++, semanticsId: 'account.sign-out')],
        ),
      ),
    );
    expect(find.text('AR'), findsOneWidget);
    expect(find.text('Sign out'), findsNothing);
    expect(byId('account'), findsOneWidget);
    await t.tap(find.text('Alex Rivera'));
    await t.pump();
    expect(find.text('Sign out'), findsOneWidget);
    expect(byId('account.sign-out'), findsOneWidget);
    await t.tap(find.text('Sign out'));
    expect(signOuts, 1);
    await expectNoOverlays(t);
    handle.dispose();
  });

  testWidgets('custom avatar replaces initials', (t) async {
    await pumpKit(t, BondAccountCard(name: 'Sam', expanded: false, onToggle: () {}, avatar: const Icon(Icons.face)));
    expect(find.byIcon(Icons.face), findsOneWidget);
    expect(find.text('S'), findsNothing);
  });
}
