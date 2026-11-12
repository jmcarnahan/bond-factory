import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  testWidgets('shows label or id, taps and removes', (t) async {
    final sem = t.ensureSemantics();
    var taps = 0;
    var removed = 0;
    await pumpAt(
      t,
      BondLinkChip(
        link: const TaskLink(kind: 'contact', id: 'c1', label: 'Dana Fox'),
        onTap: () => taps++,
        onRemove: () => removed++,
        semanticsId: 'lc',
      ),
    );
    expect(find.bySemanticsIdentifier('lc'), findsOneWidget);
    expect(find.bySemanticsIdentifier('lc-remove'), findsOneWidget);
    await t.tap(find.text('Dana Fox'));
    await t.tap(find.byIcon(Icons.close));
    expect(taps, 1);
    expect(removed, 1);
    await pumpAt(t, const BondLinkChip(link: TaskLink(kind: 'contact', id: 'c9')));
    expect(find.text('c9'), findsOneWidget);
    expect(find.byIcon(Icons.close), findsNothing, reason: 'no remove without a callback');
    sem.dispose();
  });

  testWidgets('a long name is clean at both widths', (t) async {
    await expectCleanAtBothWidths(
      t,
      () => BondLinkChip(link: TaskLink(kind: 'contact', id: 'c1', label: 'A very long contact name ' * 4), onRemove: () {}),
    );
  });
}
