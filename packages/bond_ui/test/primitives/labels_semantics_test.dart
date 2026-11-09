import 'package:bond_ui/src/labels.dart';
import 'package:bond_ui/src/primitives/bond_date_format.dart';
import 'package:bond_ui/src/semantics.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  test('English defaults for every list label', () {
    const l = BondLabels();
    expect(l.monthNames, hasLength(12));
    expect(l.monthShort, hasLength(12));
    expect(l.weekdayShort, hasLength(7));
    expect(l.weekdayShort.first, 'Mon');
  });

  testWidgets('BondLabels.of defaults without a scope, uses the scope when present',
      (t) async {
    late BondLabels bare;
    late BondLabels scoped;
    await t.pumpWidget(Builder(builder: (c) {
      bare = BondLabels.of(c);
      return BondLabelsScope(
        labels: const BondLabels(confirm: 'Si'),
        child: Builder(builder: (c2) {
          scoped = BondLabels.of(c2);
          return const SizedBox();
        }),
      );
    }));
    expect(bare.confirm, 'Confirm');
    expect(scoped.confirm, 'Si');
  });

  testWidgets('bondSemantics wraps only when something is given', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(
      t,
      Column(children: [
        bondSemantics(id: null, child: const Text('plain')),
        bondSemantics(id: 'with-id', button: true, child: const Text('x')),
      ]),
    );
    expect(find.bySemanticsIdentifier('with-id'), findsOneWidget);
    expect(bondSemantics(id: null, child: const SizedBox()), isA<SizedBox>());
    sem.dispose();
  });

  test('date formatting needs no intl', () {
    const l = BondLabels();
    expect(BondDateFormat.date(l, DateTime(2026, 11, 8)), 'Sun, Nov 8, 2026');
    expect(BondDateFormat.time(l, DateTime(2026, 1, 1, 0, 5)), '12:05 AM');
    expect(BondDateFormat.time(l, DateTime(2026, 1, 1, 13, 30)), '1:30 PM');
    expect(BondDateFormat.month(l, DateTime(2026, 2)), 'February 2026');
    expect(BondDateFormat.iso(DateTime(2026, 3, 4)), '2026-03-04');
  });
}
