import 'package:bond_ui/src/primitives/bond_segmented.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  const segments = [
    BondSegment('day', 'Day'),
    BondSegment('week', 'Week'),
    BondSegment('month', 'Month'),
  ];

  testWidgets('tapping a segment reports its value', (t) async {
    final sem = t.ensureSemantics();
    final picked = <String>[];
    await pumpBond(
      t,
      BondSegmented<String>(
        segments: segments,
        value: 'day',
        onChanged: picked.add,
        semanticsId: 'range',
      ),
    );
    expect(find.bySemanticsIdentifier('range-week'), findsOneWidget);
    await t.tap(find.text('Week'));
    await t.pump();
    expect(picked, ['week']);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('the current segment is announced as selected', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(
      t,
      BondSegmented<String>(segments: segments, value: 'week', onChanged: (_) {}),
    );
    expect(
      t.getSemantics(find.bySemanticsLabel('Week')),
      matchesSemantics(
        label: 'Week',
        isButton: true,
        isSelected: true,
        hasSelectedState: true,
        hasTapAction: true,
      ),
    );
    sem.dispose();
  });

  testWidgets('expand fills the width', (t) async {
    await pumpBond(
      t,
      BondSegmented<String>(
        segments: segments,
        value: 'day',
        expand: true,
        onChanged: (_) {},
      ),
    );
    expect(t.getSize(find.byType(BondSegmented<String>)).width, 390 - 32);
  });

  testWidgets('labels that do not fit wrap whole pills, no overflow', (t) async {
    await pumpBond(
      t,
      BondSegmented<int>(
        segments: [
          for (var i = 0; i < 6; i++) BondSegment(i, 'Option number $i'),
        ],
        value: 0,
        onChanged: (_) {},
      ),
    );
    expect(t.takeException(), isNull);
    expect(find.byType(Wrap), findsOneWidget);
  });
}
