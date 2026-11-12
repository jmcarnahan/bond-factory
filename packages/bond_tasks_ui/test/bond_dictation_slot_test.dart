import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  testWidgets('draws what the app builds, clean at both widths', (t) async {
    await expectCleanAtBothWidths(t, () => BondDictationSlot(builder: (c) => const Text('Mic here')));
    expect(find.text('Mic here'), findsOneWidget);
  });

  testWidgets('with no builder it draws nothing', (t) async {
    await pumpAt(t, const BondDictationSlot());
    expect(find.byType(Text), findsNothing);
  });
}
