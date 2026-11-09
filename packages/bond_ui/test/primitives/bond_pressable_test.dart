import 'package:bond_ui/src/primitives/bond_pressable.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  testWidgets('taps and exposes id and label', (t) async {
    final sem = t.ensureSemantics();
    var taps = 0;
    await pumpBond(
      t,
      BondPressable(
        onTap: () => taps++,
        semanticLabel: 'Open thing',
        semanticsId: 'thing',
        minSize: 48,
        child: const Text('Thing'),
      ),
    );
    expect(find.bySemanticsIdentifier('thing'), findsOneWidget);
    expect(find.bySemanticsLabel('Open thing'), findsOneWidget);
    await t.tap(find.text('Thing'));
    await t.pump();
    expect(taps, 1);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('disabled when onTap is null', (t) async {
    await pumpBond(
      t,
      const BondPressable(
        onTap: null,
        semanticLabel: 'Off',
        child: Text('Off'),
      ),
    );
    await t.tap(find.text('Off'));
    await t.pump();
    expect(find.text('Off'), findsOneWidget);
  });

  testWidgets('id alone adds an identifier without a label', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(
      t,
      BondPressable(onTap: () {}, semanticsId: 'only-id', child: const Text('x')),
    );
    expect(find.bySemanticsIdentifier('only-id'), findsOneWidget);
    sem.dispose();
  });

  testWidgets('a toggled switch renders', (t) async {
    await pumpBond(
      t,
      BondPressable(
        onTap: () {},
        semanticLabel: 'Switch',
        semanticToggled: true,
        child: const Text('s'),
      ),
    );
    expect(find.text('s'), findsOneWidget);
  });
}
