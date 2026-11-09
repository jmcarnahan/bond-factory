import 'package:bond_ui/src/primitives/bond_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  testWidgets('a plain card shows its child and has no ink', (t) async {
    await pumpBond(t, const BondCard(child: Text('Hello')));
    expect(find.text('Hello'), findsOneWidget);
    expect(find.byType(InkWell), findsNothing);
  });

  testWidgets('a tappable card fires and exposes id and label', (t) async {
    final sem = t.ensureSemantics();
    var taps = 0;
    await pumpBond(
      t,
      BondCard(
        onTap: () => taps++,
        semanticLabel: 'Open card',
        semanticsId: 'card',
        child: const Text('Body'),
      ),
    );
    expect(find.bySemanticsIdentifier('card'), findsOneWidget);
    await t.tap(find.text('Body'));
    await t.pump();
    expect(taps, 1);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('a plain card with an id carries it', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(
      t,
      const BondCard(semanticsId: 'plain', child: Text('x')),
    );
    expect(find.bySemanticsIdentifier('plain'), findsOneWidget);
    sem.dispose();
  });

  testWidgets('colour overrides are honoured', (t) async {
    await pumpBond(
      t,
      const BondCard(
        color: Color(0xFF112233),
        borderColor: Color(0xFF445566),
        child: Text('c'),
      ),
    );
    final box = t.widget<Container>(find.byType(Container).first);
    final deco = box.decoration! as BoxDecoration;
    expect(deco.color, const Color(0xFF112233));
  });
}
