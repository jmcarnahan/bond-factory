import 'package:bond_ui/src/primitives/bond_text_field.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

const _one =
    'A rather long hint that must wrap onto several lines at phone width for sure okay';
final _long = List.filled(4, _one).join(' ');

InputDecoration _decoration(WidgetTester t) =>
    t.widget<TextField>(find.byType(TextField)).decoration!;

void main() {
  testWidgets('default renders exactly as before', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(
      t,
      BondTextField(label: 'Name', hint: _long, semanticsId: 'n'),
    );
    final field = t.widget<TextField>(find.byType(TextField));
    expect(field.decoration!.hintMaxLines, 2);
    expect(field.decoration!.hintStyle, isNull);
    expect(
      field.style,
      const BondText(
        BondTokens.fallback,
      ).style(BondText.base16, BondText.regular),
    );
    expect(t.getSize(find.byType(BondTextField)), const Size(358, 97));
    final data = t
        .getSemantics(find.bySemanticsIdentifier('n'))
        .getSemanticsData();
    expect(data.label, contains('Name'));
    expect(data.flagsCollection.isTextField, isTrue);
    sem.dispose();
  });

  testWidgets('hintMaxLines: 1 cuts the hint to one line', (t) async {
    await pumpBond(
      t,
      BondTextField(label: 'Name', hint: _long, hintMaxLines: 1),
    );
    expect(_decoration(t).hintMaxLines, 1);
    expect(t.getSize(find.byType(BondTextField)).height, lessThan(97));
  });

  testWidgets('hintMaxLines: 3 lets a long hint grow the field', (t) async {
    await pumpBond(
      t,
      BondTextField(label: 'Name', hint: _long, hintMaxLines: 3),
    );
    expect(_decoration(t).hintMaxLines, 3);
    expect(t.getSize(find.byType(BondTextField)).height, greaterThan(97));
  });

  test('hintMaxLines of zero is refused', () {
    expect(() => BondTextField(hintMaxLines: 0), throwsAssertionError);
  });
}
