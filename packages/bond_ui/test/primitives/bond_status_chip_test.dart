import 'package:bond_ui/src/primitives/bond_status_chip.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  test('tone names map to roles, unknown is neutral', () {
    expect(bondToneFromName('positive'), BondToneRole.positive);
    expect(bondToneFromName('caution'), BondToneRole.caution);
    expect(bondToneFromName('red'), BondToneRole.danger);
    expect(bondToneFromName('danger'), BondToneRole.danger);
    expect(bondToneFromName('info'), BondToneRole.info);
    expect(bondToneFromName('neutral'), isNull);
    expect(bondToneFromName('whatever'), isNull);
  });

  test('fromWire gives a positive status a check', () {
    expect(BondStatus.fromWire('Paid', 'positive').icon, Icons.check);
    expect(BondStatus.fromWire('Late', 'red').icon, isNull);
    expect(BondStatus.fromWire('Late', 'red').tone, BondToneRole.danger);
  });

  testWidgets('renders label, icon and tone colours', (t) async {
    await pumpBond(
      t,
      const BondStatusChip(
        BondStatus('Paid', tone: BondToneRole.positive, icon: Icons.check),
      ),
    );
    expect(find.text('Paid'), findsOneWidget);
    expect(find.byIcon(Icons.check), findsOneWidget);
    final deco = t
        .widget<Container>(find.descendant(
            of: find.byType(BondStatusChip),
            matching: find.byType(Container)))
        .decoration! as BoxDecoration;
    expect(deco.color, BondTokens.fallback.positive.wash);
    await expectNoOverlays(t);
  });

  testWidgets('carries the id and wraps a long label at phone width', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(
      t,
      const BondStatusChip(
        BondStatus(
            'Past the deadline by a long time and needs someone to look at it today, please'),
        semanticsId: 'status',
      ),
    );
    expect(find.bySemanticsIdentifier('status'), findsOneWidget);
    expect(t.takeException(), isNull);
    sem.dispose();
  });
}
