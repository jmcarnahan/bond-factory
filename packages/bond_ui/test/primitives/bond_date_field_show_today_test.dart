import 'dart:ui';

import 'package:bond_ui/src/primitives/bond_button.dart';
import 'package:bond_ui/src/primitives/bond_date_field.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  final today = DateTime(2026, 11, 8);
  final value = DateTime(2026, 11, 10);
  void changed(DateTime _) {}
  void cleared() {}

  Finder today_(String id) => find.bySemanticsIdentifier('$id-today');
  Finder clear_(String id) => find.bySemanticsIdentifier('$id-clear');

  testWidgets('default renders exactly as before: closed', (t) async {
    await pumpBond(
      t,
      BondDateField(
        value: value,
        today: today,
        semanticsId: 'd',
        onChanged: changed,
      ),
    );
    expect(t.getSize(find.byType(BondDateField)), const Size(358, 44));
    expect(find.byType(BondButton), findsNothing);
  });

  testWidgets('default renders exactly as before: open', (t) async {
    final sem = t.ensureSemantics();
    final picked = <DateTime>[];
    await pumpBond(
      t,
      BondDateField(
        value: value,
        today: today,
        initiallyOpen: true,
        semanticsId: 'd',
        onChanged: picked.add,
        onCleared: cleared,
      ),
    );
    expect(t.getSize(find.byType(BondDateField)), const Size(358, 394));
    final todayButton = t.widget<BondButton>(
      find.widgetWithText(BondButton, 'Today'),
    );
    expect(todayButton.variant, BondButtonVariant.quiet);
    expect(
      t
          .widget<Text>(
            find.descendant(
              of: find.widgetWithText(BondButton, 'Today'),
              matching: find.text('Today'),
            ),
          )
          .style,
      const BondText(BondTokens.fallback).style(
        BondText.small14,
        BondText.semibold,
        color: BondTokens.fallback.ink,
      ),
    );
    expect(find.widgetWithText(BondButton, 'Clear'), findsOneWidget);
    for (final id in ['d-today', 'd-clear']) {
      final data = t
          .getSemantics(find.bySemanticsIdentifier(id))
          .getSemanticsData();
      expect(data.hasAction(SemanticsAction.tap), isTrue);
    }
    expect(t.getSemantics(today_('d')).label, 'Today');
    expect(t.getSemantics(clear_('d')).label, 'Clear');
    await t.tap(find.text('Today'));
    await t.pump();
    expect(picked, [DateTime(2026, 11, 8)]);
    sem.dispose();
  });

  testWidgets('default renders exactly as before: no Clear without onCleared', (
    t,
  ) async {
    final sem = t.ensureSemantics();
    await pumpBond(
      t,
      BondDateField(
        value: value,
        today: today,
        initiallyOpen: true,
        semanticsId: 'd',
        onChanged: changed,
      ),
    );
    expect(today_('d'), findsOneWidget);
    expect(clear_('d'), findsNothing);
    sem.dispose();
  });

  testWidgets('default renders exactly as before: dateTime mode', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(
      t,
      BondDateField(
        value: value,
        today: today,
        mode: BondDateMode.dateTime,
        initiallyOpen: true,
        semanticsId: 'd',
        onChanged: changed,
        onCleared: cleared,
      ),
    );
    expect(today_('d'), findsOneWidget);
    expect(clear_('d'), findsOneWidget);
    expect(find.widgetWithText(BondButton, 'Today'), findsOneWidget);
    sem.dispose();
  });

  testWidgets('default renders exactly as before: no value', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(
      t,
      BondDateField(
        value: null,
        today: today,
        initiallyOpen: true,
        semanticsId: 'd',
        onChanged: changed,
        onCleared: cleared,
      ),
    );
    expect(today_('d'), findsOneWidget);
    expect(clear_('d'), findsNothing);
    sem.dispose();
  });

  testWidgets('showToday: false hides Today, keeps Clear', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(
      t,
      BondDateField(
        value: value,
        today: today,
        initiallyOpen: true,
        semanticsId: 'd',
        onChanged: changed,
        onCleared: cleared,
        showToday: false,
      ),
    );
    expect(today_('d'), findsNothing);
    expect(find.text('Today'), findsNothing);
    expect(clear_('d'), findsOneWidget);
    expect(find.text('Clear'), findsOneWidget);
    sem.dispose();
  });

  testWidgets('showToday: false with no Clear draws no footer', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(
      t,
      BondDateField(
        value: value,
        today: today,
        initiallyOpen: true,
        semanticsId: 'd',
        onChanged: changed,
        showToday: false,
      ),
    );
    expect(find.byType(BondButton), findsNothing);
    expect(find.text('Today'), findsNothing);
    expect(find.text('Clear'), findsNothing);
    expect(today_('d'), findsNothing);
    expect(clear_('d'), findsNothing);
    sem.dispose();
  });

  testWidgets('time mode is unchanged by showToday', (t) async {
    await pumpBond(
      t,
      BondDateField(
        value: value,
        today: today,
        mode: BondDateMode.time,
        initiallyOpen: true,
        onChanged: changed,
        showToday: false,
      ),
    );
    final off = t.getSize(find.byType(BondDateField));
    expect(find.byType(BondButton), findsNothing);
    await t.pumpWidget(const SizedBox());
    await pumpBond(
      t,
      BondDateField(
        value: value,
        today: today,
        mode: BondDateMode.time,
        initiallyOpen: true,
        onChanged: changed,
      ),
    );
    expect(t.getSize(find.byType(BondDateField)), off);
    expect(find.byType(BondButton), findsNothing);
  });
}
