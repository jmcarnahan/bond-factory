import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/shell/bond_bottom_nav.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../components/kit_host.dart';

void main() {
  testWidgets('selects an item, shows badge, ids and spoken count', (t) async {
    setPhone(t);
    final handle = t.ensureSemantics();
    var index = 0;
    await pumpKit(
      t,
      StatefulBuilder(
        builder: (context, set) => Align(
          alignment: Alignment.bottomCenter,
          child: BondBottomNav(
            currentIndex: index,
            onTap: (i) => set(() => index = i),
            items: const [
              BondBottomNavItem(icon: Icons.home, label: 'Home', semanticsId: 'nav.home'),
              BondBottomNavItem(icon: Icons.mail, label: 'Messages', badge: 120, semanticsId: 'nav.messages'),
              BondBottomNavItem(icon: Icons.person, label: 'A very long label here', semanticsId: 'nav.me'),
              BondBottomNavItem(icon: Icons.settings, label: 'More', semanticsId: 'nav.more'),
              BondBottomNavItem(icon: Icons.info, label: 'Help', semanticsId: 'nav.help'),
            ],
          ),
        ),
      ),
    );
    expect(byId('nav.messages'), findsOneWidget);
    expect(find.text('99+'), findsOneWidget);
    expect(find.bySemanticsLabel('Messages, 120'), findsOneWidget);
    await t.tap(find.text('Messages'));
    await t.pump();
    expect(index, 1);
    await expectNoOverlays(t);
    expect(t.takeException(), isNull);
    handle.dispose();
  });
}
