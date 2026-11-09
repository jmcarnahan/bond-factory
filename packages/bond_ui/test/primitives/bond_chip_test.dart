import 'package:bond_ui/src/primitives/bond_chip.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  testWidgets('tap fires and the id is exposed', (t) async {
    final sem = t.ensureSemantics();
    var taps = 0;
    await pumpBond(
      t,
      BondChip(label: 'Open', onTap: () => taps++, semanticsId: 'chip-open'),
    );
    expect(find.bySemanticsIdentifier('chip-open'), findsOneWidget);
    await t.tap(find.text('Open'));
    await t.pump();
    expect(taps, 1);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('a count is drawn and spoken with the label', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(
      t,
      BondChip(label: 'Late', count: 3, countLabel: '3+', onTap: () {}),
    );
    expect(find.text('3+'), findsOneWidget);
    expect(find.bySemanticsLabel('Late, 3+'), findsOneWidget);
    sem.dispose();
  });

  testWidgets('selected uses the ink fill; a tone uses its wash', (t) async {
    await pumpBond(
      t,
      const Column(children: [
        BondChip(label: 'Sel', selected: true),
        BondChip(label: 'Toned', tone: BondToneRole.caution),
      ]),
    );
    BoxDecoration deco(String label) => t
        .widget<Container>(find
            .ancestor(of: find.text(label), matching: find.byType(Container))
            .first)
        .decoration! as BoxDecoration;
    expect(deco('Sel').color, BondTokens.fallback.ink);
    expect(deco('Toned').color, BondTokens.fallback.caution.wash);
  });

  testWidgets('a long label wraps and nothing overflows at phone width', (t) async {
    await pumpBond(
      t,
      const BondChip(
        label: 'A reason the server wrote that is far too long for one line '
            'on a phone screen and must wrap',
        count: 12,
      ),
    );
    expect(t.takeException(), isNull);
  });
}
