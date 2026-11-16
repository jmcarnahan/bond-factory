import 'package:bond_ui/src/primitives/bond_status_chip.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

const _long =
    'A rather long label that must wrap onto several lines at phone width for sure okay';

Text _label(WidgetTester t) => t.widget<Text>(
  find.descendant(of: find.byType(BondStatusChip), matching: find.text(_long)),
);

void main() {
  final tokens = BondTokens.fallback;

  testWidgets('default renders exactly as before', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(
      t,
      const BondStatusChip(BondStatus(_long), semanticsId: 's'),
    );
    expect(t.getSize(find.byType(BondStatusChip)), const Size(358, 90));
    final text = _label(t);
    expect(text.maxLines, isNull);
    expect(text.overflow, isNull);
    expect(
      text.style,
      BondText(tokens).style(
        BondText.label13,
        BondText.semibold,
        color: tokens.colorsFor(null).foreground,
      ),
    );
    expect(find.bySemanticsIdentifier('s'), findsOneWidget);
    expect(
      t
          .getSemantics(
            find.descendant(
              of: find.byType(BondStatusChip),
              matching: find.text(_long),
            ),
          )
          .label,
      _long,
    );
    sem.dispose();
  });

  testWidgets('maxLines caps the label with an ellipsis', (t) async {
    await pumpBond(t, const BondStatusChip(BondStatus(_long), maxLines: 1));
    final text = _label(t);
    expect(text.maxLines, 1);
    expect(text.overflow, TextOverflow.ellipsis);
    expect(t.getSize(find.byType(BondStatusChip)), const Size(358, 30));
  });

  test('maxLines of zero is refused', () {
    expect(
      () => BondStatusChip(const BondStatus('x'), maxLines: 0),
      throwsAssertionError,
    );
  });
}
