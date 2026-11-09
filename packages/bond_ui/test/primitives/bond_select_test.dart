import 'package:bond_ui/src/primitives/bond_select.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  const options = [
    BondOption('a', 'Alpha'),
    BondOption('b', 'Bravo'),
    BondOption('c', 'Charlie'),
  ];

  Widget select({
    BondSelectVariant variant = BondSelectVariant.chips,
    String? value,
    required List<String> picked,
    bool searchable = false,
    String? id = 'pick',
  }) =>
      BondSelect<String>(
        options: options,
        value: value,
        variant: variant,
        label: 'Letter',
        searchable: searchable,
        semanticsId: id,
        onChanged: picked.add,
      );

  testWidgets('chips pick and carry per-option ids', (t) async {
    final sem = t.ensureSemantics();
    final picked = <String>[];
    await pumpBond(t, select(picked: picked, value: 'a'));
    expect(find.text('Letter'), findsOneWidget);
    expect(find.bySemanticsIdentifier('pick-b'), findsOneWidget);
    await t.tap(find.text('Bravo'));
    await t.pump();
    expect(picked, ['b']);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('segmented picks', (t) async {
    final picked = <String>[];
    await pumpBond(
      t,
      select(variant: BondSelectVariant.segmented, picked: picked, value: 'a'),
    );
    await t.tap(find.text('Charlie'));
    await t.pump();
    expect(picked, ['c']);
    await expectNoOverlays(t);
  });

  testWidgets('radio list picks and filters when searchable', (t) async {
    final sem = t.ensureSemantics();
    final picked = <String>[];
    await pumpBond(
      t,
      select(
        variant: BondSelectVariant.radioList,
        picked: picked,
        value: 'a',
        searchable: true,
      ),
    );
    expect(find.byIcon(Icons.radio_button_checked), findsOneWidget);
    expect(find.bySemanticsIdentifier('pick-c'), findsOneWidget);
    await t.enterText(find.byType(TextField), 'brav');
    await t.pump();
    expect(find.text('Alpha'), findsNothing);
    await t.tap(find.text('Bravo'));
    await t.pump();
    expect(picked, ['b']);
    await t.enterText(find.byType(TextField), 'zzz');
    await t.pump();
    expect(find.text('No results'), findsOneWidget);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('expanding opens inline, picks, and closes with no overlay',
      (t) async {
    final sem = t.ensureSemantics();
    final picked = <String>[];
    await pumpBond(
      t,
      select(variant: BondSelectVariant.expanding, picked: picked),
    );
    // Closed: shows the placeholder, no options yet.
    expect(find.text('Select'), findsOneWidget);
    expect(find.text('Alpha'), findsNothing);
    await t.tap(find.text('Select'));
    await t.pump();
    expect(find.text('Alpha'), findsOneWidget);
    expect(find.text('Charlie'), findsOneWidget);
    await expectNoOverlays(t);
    await t.tap(find.text('Charlie'));
    await t.pump();
    expect(picked, ['c']);
    // Picking collapses the list.
    expect(find.text('Alpha'), findsNothing);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('expanding shows the chosen label and has an id', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(
      t,
      select(
        variant: BondSelectVariant.expanding,
        picked: <String>[],
        value: 'b',
      ),
    );
    expect(find.text('Bravo'), findsOneWidget);
    expect(find.bySemanticsIdentifier('pick'), findsOneWidget);
    sem.dispose();
  });

  testWidgets('a placeholder replaces the default text', (t) async {
    await pumpBond(
      t,
      BondSelect<String>(
        options: options,
        value: null,
        variant: BondSelectVariant.expanding,
        placeholder: 'Choose one',
        onChanged: (_) {},
      ),
    );
    expect(find.text('Choose one'), findsOneWidget);
  });
}
