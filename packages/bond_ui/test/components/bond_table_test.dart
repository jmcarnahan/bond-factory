import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/components/bond_table.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'kit_host.dart';

BondTable _table({ValueChanged<int>? onTap, bool Function(int)? tappable}) => BondTable(
      columns: const [BondColumn('Name', flex: 2), BondColumn('Status'), BondColumn('Total', alignEnd: true)],
      rows: const [
        [Text('Alpha'), Text('Open'), Text('10')],
        [Text('Beta'), Text('Closed'), Text('20')],
      ],
      onRowTap: onTap,
      rowTappable: tappable,
      semanticsId: 'tbl',
    );

void main() {
  testWidgets('wide: header row and one line per row', (t) async {
    setWideScreen(t);
    await pumpKit(t, _table());
    expect(find.text('NAME'), findsOneWidget);
    expect(find.text('Alpha'), findsOneWidget);
    expect(find.text('Name'), findsNothing);
  });

  testWidgets('phone width stacks rows with a label per value', (t) async {
    setPhone(t);
    await pumpKit(t, _table());
    expect(find.text('NAME'), findsNothing);
    expect(find.text('Name'), findsNWidgets(2));
    expect(find.text('Total'), findsNWidgets(2));
    expect(find.text('Beta'), findsOneWidget);
    expect(t.takeException(), isNull);
  });

  testWidgets('row tap reports the index, honours rowTappable, exposes ids', (t) async {
    setPhone(t);
    final handle = t.ensureSemantics();
    final taps = <int>[];
    await pumpKit(t, _table(onTap: taps.add, tappable: (r) => r == 0));
    await t.tap(find.text('Alpha'));
    await t.tap(find.text('Beta'));
    expect(taps, [0]);
    expect(byId('tbl-row-0'), findsOneWidget);
    expect(byId('tbl-row-1'), findsNothing);
    await expectNoOverlays(t);
    handle.dispose();
  });

  testWidgets('empty text and footer show inline', (t) async {
    setWideScreen(t);
    await pumpKit(
      t,
      const BondTable(columns: [BondColumn('Name')], rows: [], emptyText: 'No rows', footer: Text('Showing 0')),
    );
    expect(find.text('No rows'), findsOneWidget);
    expect(find.text('Showing 0'), findsOneWidget);
  });
}
