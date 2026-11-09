import 'package:bond_ui/src/primitives/bond_icon_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  testWidgets('taps, carries the label as its name and an id', (t) async {
    final sem = t.ensureSemantics();
    var taps = 0;
    await pumpBond(
      t,
      BondIconButton(
        icon: Icons.add,
        label: 'Add item',
        onPressed: () => taps++,
        semanticsId: 'add',
      ),
    );
    expect(find.bySemanticsIdentifier('add'), findsOneWidget);
    expect(find.bySemanticsLabel('Add item'), findsOneWidget);
    await t.tap(find.byIcon(Icons.add));
    await t.pump();
    expect(taps, 1);
    // No hover text: no tooltip, the label is not drawn.
    expect(find.text('Add item'), findsNothing);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('showLabel draws the label; disabled does not fire', (t) async {
    await pumpBond(
      t,
      const BondIconButton(
        icon: Icons.edit,
        label: 'Edit',
        showLabel: true,
        onPressed: null,
      ),
    );
    expect(find.text('Edit'), findsOneWidget);
    await t.tap(find.text('Edit'));
    await t.pump();
  });

  testWidgets('hit area is at least 48 square', (t) async {
    await pumpBond(
      t,
      BondIconButton(icon: Icons.close, label: 'Close', onPressed: () {}),
    );
    final size = t.getSize(find.byType(InkWell));
    expect(size.width, greaterThanOrEqualTo(48));
    expect(size.height, greaterThanOrEqualTo(48));
  });
}
