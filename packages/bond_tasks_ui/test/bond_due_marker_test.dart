import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  testWidgets('shows the count, nothing for zero', (t) async {
    await pumpAt(t, const BondDueMarker(count: 3));
    expect(find.text('3'), findsOneWidget);
    await pumpAt(t, const BondDueMarker(count: 0));
    expect(find.text('0'), findsNothing);
  });

  testWidgets('speaks "overdue" or "due" with the count and exposes its id', (t) async {
    final sem = t.ensureSemantics();
    await pumpAt(t, const BondDueMarker(count: 2, overdue: true, semanticsId: 'm'));
    expect(find.bySemanticsLabel('2 overdue'), findsOneWidget);
    expect(find.bySemanticsIdentifier('m'), findsOneWidget);
    await pumpAt(t, const BondDueMarker(count: 4));
    expect(find.bySemanticsLabel('4 due'), findsOneWidget);
    sem.dispose();
  });

  testWidgets('overdue and plain markers differ in colour', (t) async {
    Color? fill() => ((t.widget<Container>(find.descendant(of: find.byType(BondDueMarker), matching: find.byType(Container)))
            .decoration) as BoxDecoration)
        .color;
    await pumpAt(t, const BondDueMarker(count: 1));
    final plain = fill();
    await pumpAt(t, const BondDueMarker(count: 1, overdue: true));
    expect(fill(), isNot(plain));
  });

  testWidgets('in a grid the cell speaks the marker through daySemantics', (t) async {
    final sem = t.ensureSemantics();
    const labels = TaskLabels();
    await pumpAt(
      t,
      BondMonthGrid(
        visibleMonth: DateTime(2026, 3),
        selected: null,
        today: kToday,
        onPrevious: () {},
        onNext: () {},
        onSelect: (_) {},
        isSelectable: (_) => true,
        dayBuilder: (c, d) => d.day == 12 ? const BondDueMarker(count: 2, overdue: true) : const SizedBox.shrink(),
        daySemantics: (d) => d.day == 12 ? labels.markerText(2, overdue: true) : '',
      ),
    );
    expect(find.bySemanticsLabel('12, 2 overdue'), findsOneWidget);
    sem.dispose();
  });

  for (final phone in [false, true]) {
    testWidgets('sits in a month grid cell without overflow (phone=$phone)', (t) async {
      await pumpAt(
        t,
        BondMonthGrid(
          visibleMonth: DateTime(2026, 3),
          selected: null,
          today: kToday,
          onPrevious: () {},
          onNext: () {},
          onSelect: (_) {},
          isSelectable: (_) => true,
          dayBuilder: (c, d) => d.day == 12 ? const BondDueMarker(count: 12, overdue: true) : const SizedBox.shrink(),
        ),
        phone: phone,
      );
      expect(find.text('12'), findsNWidgets(2), reason: 'the day number and the count');
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
    });
  }
}
