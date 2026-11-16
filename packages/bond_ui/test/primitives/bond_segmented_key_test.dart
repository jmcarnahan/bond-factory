import 'dart:ui';

import 'package:bond_ui/src/primitives/bond_pressable.dart';
import 'package:bond_ui/src/primitives/bond_segmented.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  final tokens = BondTokens.fallback;

  testWidgets('default renders exactly as before', (t) async {
    final sem = t.ensureSemantics();
    final log = <int>[];
    await pumpBond(
      t,
      BondSegmented<int>(
        segments: const [BondSegment(1, 'A'), BondSegment(2, 'B')],
        value: 1,
        onChanged: log.add,
        semanticsId: 'r',
      ),
    );
    expect(t.getSize(find.byType(BondSegmented<int>)), const Size(104, 44));
    expect(find.byType(BondPressable), findsNWidgets(2));
    for (final p in t.widgetList<BondPressable>(find.byType(BondPressable))) {
      expect(p.key, isNull);
    }
    expect(
      t.widget<Text>(find.text('A')).style,
      BondText(
        tokens,
      ).style(BondText.small14, BondText.semibold, color: tokens.ink),
    );
    expect(
      t.widget<Text>(find.text('B')).style,
      BondText(
        tokens,
      ).style(BondText.small14, BondText.medium, color: tokens.muted),
    );
    final a = t
        .getSemantics(find.bySemanticsIdentifier('r-1'))
        .getSemanticsData();
    final b = t
        .getSemantics(find.bySemanticsIdentifier('r-2'))
        .getSemanticsData();
    expect(a.label, 'A');
    expect(b.label, 'B');
    expect(a.hasAction(SemanticsAction.tap), isTrue);
    expect(b.hasAction(SemanticsAction.tap), isTrue);
    expect(a.flagsCollection.isSelected, isNot(b.flagsCollection.isSelected));
    await t.tap(find.text('B'));
    expect(log, [2]);
    sem.dispose();
  });

  test('a segment has no key unless given one', () {
    expect(const BondSegment(1, 'A').key, isNull);
  });

  testWidgets('a segment key lands on its tappable', (t) async {
    final log = <int>[];
    await pumpBond(
      t,
      BondSegmented<int>(
        segments: const [
          BondSegment(1, 'A'),
          BondSegment(2, 'B', key: ValueKey('two')),
        ],
        value: 1,
        onChanged: log.add,
      ),
    );
    expect(t.getSize(find.byType(BondSegmented<int>)), const Size(104, 44));
    expect(find.byKey(const ValueKey('two')), findsOneWidget);
    expect(t.widget(find.byKey(const ValueKey('two'))), isA<BondPressable>());
    await t.tap(find.byKey(const ValueKey('two')));
    expect(log, [2]);
  });
}
