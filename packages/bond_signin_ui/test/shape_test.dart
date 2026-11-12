import 'package:bond_connections/bond_connections.dart';
import 'package:bond_signin/bond_signin.dart';
import 'package:bond_signin_ui/bond_signin_ui.dart';
import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('a custom shape reaches the scope ask card', (t) async {
    setPhone(t);
    await pumpApp(
      t,
      BondScopeAskCard(
        wanted: const [WantedSet(id: 'calendar', provider: 'google', label: 'Calendar')],
        labels: const SignInLabels(),
        onAsk: (_) async {},
      ),
      theme: BondTheme.build(BondTokens.fallback.copyWith(shape: const BondShape(r12: 3))),
    );
    final radii = t
        .widgetList<Container>(find.descendant(of: find.byType(BondScopeAskCard), matching: find.byType(Container)))
        .map((c) => c.decoration)
        .whereType<BoxDecoration>()
        .map((d) => d.borderRadius);
    expect(radii, contains(BorderRadius.circular(3)));
  });
}
