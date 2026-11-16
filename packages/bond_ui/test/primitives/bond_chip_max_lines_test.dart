import 'dart:ui';

import 'package:bond_ui/src/primitives/bond_chip.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

const _long =
    'A rather long label that must wrap onto several lines at phone width for sure okay';

Text _label(WidgetTester t) => t.widget<Text>(
  find.descendant(of: find.byType(BondChip), matching: find.text(_long)),
);

void main() {
  final tokens = BondTokens.fallback;

  testWidgets('default renders exactly as before', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(t, BondChip(label: _long, onTap: () {}, semanticsId: 'c'));
    expect(t.getSize(find.byType(BondChip)), const Size(358, 94));
    final text = _label(t);
    expect(text.maxLines, isNull);
    expect(text.overflow, isNull);
    expect(
      text.style,
      BondText(tokens).style(
        BondText.small14,
        BondText.medium,
        color: tokens.colorsFor(null).foreground,
      ),
    );
    expect(
      t
          .getSemantics(
            find.descendant(
              of: find.byType(BondChip),
              matching: find.text(_long),
            ),
          )
          .label,
      _long,
    );
    final data = t
        .getSemantics(find.bySemanticsIdentifier('c'))
        .getSemanticsData();
    expect(data.hasAction(SemanticsAction.tap), isTrue);
    expect(data.flagsCollection.isButton, isTrue);
    sem.dispose();
  });

  testWidgets('maxLines caps the label with an ellipsis', (t) async {
    await pumpBond(t, const BondChip(label: _long, maxLines: 1));
    final text = _label(t);
    expect(text.maxLines, 1);
    expect(text.overflow, TextOverflow.ellipsis);
    expect(t.getSize(find.byType(BondChip)), const Size(358, 36));
  });

  test('maxLines of zero is refused', () {
    expect(() => BondChip(label: 'x', maxLines: 0), throwsAssertionError);
  });
}
