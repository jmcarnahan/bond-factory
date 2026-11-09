import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/components/bond_tabs.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'kit_host.dart';

void main() {
  testWidgets('tapping a tab switches and reports its index', (t) async {
    setPhone(t);
    final handle = t.ensureSemantics();
    var index = 0;
    await pumpKit(
      t,
      StatefulBuilder(
        builder: (context, set) => BondTabs(
          tabs: const [
            BondTab('Overview', semanticsId: 'tabs.overview'),
            BondTab('People', count: 3, semanticsId: 'tabs.people'),
            BondTab('History', semanticsId: 'tabs.history'),
          ],
          index: index,
          onChanged: (i) => set(() => index = i),
        ),
      ),
    );
    expect(byId('tabs.overview'), findsOneWidget);
    expect(byId('tabs.people'), findsOneWidget);
    await t.tap(find.text('People'));
    await t.pump();
    expect(index, 1);
    await t.tap(find.text('History'));
    await t.pump();
    expect(index, 2);
    await expectNoOverlays(t);
    handle.dispose();
  });

  testWidgets('many tabs scroll sideways at phone width without overflow', (t) async {
    setPhone(t);
    await pumpKit(
      t,
      BondTabs(
        tabs: [for (var i = 0; i < 8; i++) BondTab('Section number $i')],
        index: 0,
        onChanged: (_) {},
      ),
    );
    expect(t.takeException(), isNull);
  });
}
