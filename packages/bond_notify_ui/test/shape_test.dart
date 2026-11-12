import 'package:bond_notify_ui/bond_notify_ui.dart';
import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('a custom shape reaches the unread badge', (t) async {
    setPhone(t);
    await pumpApp(
      t,
      const BondNoticeBadge(unread: 3),
      theme: BondTheme.build(BondTokens.fallback.copyWith(shape: const BondShape(r12: 3))),
    );
    final radii = t
        .widgetList<Container>(find.descendant(of: find.byType(BondNoticeBadge), matching: find.byType(Container)))
        .map((c) => c.decoration)
        .whereType<BoxDecoration>()
        .map((d) => d.borderRadius);
    expect(radii, contains(BorderRadius.circular(3)));
  });
}
