import 'package:bond_ui/src/primitives/bond_avatar.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  testWidgets('shows initials in a circle sized by size', (t) async {
    await pumpBond(t, const BondAvatar(initials: 'AB', size: 48));
    expect(find.text('AB'), findsOneWidget);
    expect(t.getSize(find.byType(BondAvatar)), const Size(48, 48));
    await expectNoOverlays(t);
  });

  testWidgets('defaults to ink fill and on-fill initials', (t) async {
    await pumpBond(t, const BondAvatar(initials: 'CD'));
    final deco = t
        .widget<Container>(find.descendant(
            of: find.byType(BondAvatar), matching: find.byType(Container)))
        .decoration! as BoxDecoration;
    expect(deco.color, BondTokens.fallback.ink);
    expect(deco.shape, BoxShape.circle);
    final style = t.widget<Text>(find.text('CD')).style!;
    expect(style.color, BondTokens.fallback.onFill);
  });

  testWidgets('colours can be overridden', (t) async {
    await pumpBond(
      t,
      BondAvatar(
        initials: 'EF',
        color: BondTokens.fallback.personColor(2),
        foreground: BondTokens.fallback.ink,
      ),
    );
    final deco = t
        .widget<Container>(find.descendant(
            of: find.byType(BondAvatar), matching: find.byType(Container)))
        .decoration! as BoxDecoration;
    expect(deco.color, BondTokens.fallback.personColor(2));
  });
}
