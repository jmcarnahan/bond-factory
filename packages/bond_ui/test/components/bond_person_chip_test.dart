import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/components/bond_person_chip.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'kit_host.dart';

Color _dotColor(WidgetTester t, int slot) {
  final box = t.widget<Container>(find.byKey(ValueKey('bond-person-dot-$slot')));
  return (box.decoration! as BoxDecoration).color!;
}

void main() {
  testWidgets('dot colour comes from the person palette and wraps', (t) async {
    final palette = BondTokens.fallback.personPalette;
    await pumpKit(t, const Column(children: [BondPersonChip(label: 'Alex', slot: 0), BondPersonChip(label: 'Sam', slot: 7)]));
    expect(_dotColor(t, 0), palette[0]);
    expect(_dotColor(t, 7), palette[7 % palette.length]);
    expect(find.text('Alex'), findsOneWidget);
    await expectNoOverlays(t);
  });

  testWidgets('no slot is a dashed chip with the generic label', (t) async {
    final handle = t.ensureSemantics();
    await pumpKit(t, const BondPersonChip(semanticsId: 'chip'));
    expect(find.text('Unassigned'), findsOneWidget);
    expect(find.byKey(const ValueKey('bond-person-dot-0')), findsNothing);
    expect(byId('chip'), findsOneWidget);
    await expectNoOverlays(t);
    handle.dispose();
  });
}
