import 'dart:ui';

import 'package:bond_ui/src/components/bond_tabs.dart';
import 'package:bond_ui/src/primitives/bond_pressable.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'kit_host.dart';

void main() {
  final tokens = BondTokens.fallback;

  testWidgets('default renders exactly as before', (t) async {
    final sem = t.ensureSemantics();
    final log = <int>[];
    await pumpKit(
      t,
      BondTabs(
        tabs: const [
          BondTab('A', semanticsId: 'ta'),
          BondTab('B', count: 3, semanticsId: 'tb'),
        ],
        index: 0,
        onChanged: log.add,
      ),
    );
    final size = t.getSize(find.byType(BondTabs));
    expect(size.height, 49);
    expect(size.width, 113);
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
        .getSemantics(find.bySemanticsIdentifier('ta'))
        .getSemanticsData();
    final b = t
        .getSemantics(find.bySemanticsIdentifier('tb'))
        .getSemanticsData();
    expect(a.label, 'A');
    expect(b.label, 'B, 3');
    expect(a.hasAction(SemanticsAction.tap), isTrue);
    expect(b.hasAction(SemanticsAction.tap), isTrue);
    expect(a.flagsCollection.isButton, isTrue);
    expect(a.flagsCollection.isSelected, isNot(b.flagsCollection.isSelected));
    await t.tap(find.text('B'));
    expect(log, [1]);
    sem.dispose();
  });

  test('a tab has no key unless given one', () {
    expect(const BondTab('A').key, isNull);
  });

  testWidgets('a tab key lands on its tappable', (t) async {
    final log = <int>[];
    await pumpKit(
      t,
      BondTabs(
        tabs: const [
          BondTab('A'),
          BondTab('B', key: ValueKey('bee')),
        ],
        index: 0,
        onChanged: log.add,
      ),
    );
    expect(t.getSize(find.byType(BondTabs)).height, 49);
    expect(find.byKey(const ValueKey('bee')), findsOneWidget);
    expect(t.widget(find.byKey(const ValueKey('bee'))), isA<BondPressable>());
    await t.tap(find.byKey(const ValueKey('bee')));
    expect(log, [1]);
  });
}
