import 'dart:ui';

import 'package:bond_ui/src/components/bond_deactivated.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'kit_host.dart';

Scaffold _scaffold(WidgetTester t) => t.widget<Scaffold>(
  find.descendant(
    of: find.byType(BondDeactivated),
    matching: find.byType(Scaffold),
  ),
);

void main() {
  testWidgets('default renders exactly as before', (t) async {
    final sem = t.ensureSemantics();
    var out = 0;
    await pumpKit(
      t,
      BondDeactivated(
        title: 'Account off',
        body: 'Ask an admin.',
        signOutLabel: 'Sign out',
        onSignOut: () => out++,
        signOutSemanticsId: 'so',
      ),
    );
    expect(_scaffold(t).backgroundColor, BondTokens.fallback.surface);
    expect(t.getSize(find.byType(BondDeactivated)), const Size(800, 600));
    final column = find.descendant(
      of: find.byType(BondDeactivated),
      matching: find.byType(Column),
    );
    expect(t.getSize(column.first), const Size(420, 188));
    expect(
      t.widget<Text>(find.text('Account off')).style,
      const BondText(BondTokens.fallback).title,
    );
    final data = t
        .getSemantics(find.bySemanticsIdentifier('so'))
        .getSemanticsData();
    expect(data.label, 'Sign out');
    expect(data.hasAction(SemanticsAction.tap), isTrue);
    await t.tap(find.text('Sign out'));
    expect(out, 1);
    sem.dispose();
  });

  testWidgets('backgroundColor replaces the surface colour', (t) async {
    await pumpKit(
      t,
      BondDeactivated(
        title: 'Account off',
        body: 'Ask an admin.',
        signOutLabel: 'Sign out',
        onSignOut: () {},
        backgroundColor: BondTokens.fallback.line,
      ),
    );
    expect(_scaffold(t).backgroundColor, BondTokens.fallback.line);
  });
}
