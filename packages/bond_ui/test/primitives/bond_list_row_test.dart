import 'package:bond_ui/src/primitives/bond_list_row.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  testWidgets('shows lanes and fires onTap; id is exposed', (t) async {
    final sem = t.ensureSemantics();
    var taps = 0;
    await pumpBond(
      t,
      BondListRow(
        title: 'Row title',
        subtitle: 'Row subtitle',
        leading: const Icon(Icons.person),
        trailing: const Text('Trail'),
        onTap: () => taps++,
        semanticsId: 'row',
      ),
    );
    expect(find.text('Row title'), findsOneWidget);
    expect(find.text('Row subtitle'), findsOneWidget);
    expect(find.byIcon(Icons.person), findsOneWidget);
    expect(find.text('Trail'), findsOneWidget);
    expect(find.bySemanticsIdentifier('row'), findsOneWidget);
    await t.tap(find.text('Row title'));
    await t.pump();
    expect(taps, 1);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('compact drops the lanes; accent draws a bar', (t) async {
    await pumpBond(
      t,
      const BondListRow(
        title: 'Compact',
        compact: true,
        leading: Icon(Icons.person),
        trailing: Text('Trail'),
        accent: Color(0xFF336699),
      ),
    );
    expect(find.byIcon(Icons.person), findsNothing);
    expect(find.text('Trail'), findsNothing);
    expect(find.text('Compact'), findsOneWidget);
  });

  testWidgets('done strikes the title through and mutes it', (t) async {
    await pumpBond(t, const BondListRow(title: 'Finished', done: true));
    final style = t.widget<Text>(find.text('Finished')).style!;
    expect(style.decoration, TextDecoration.lineThrough);
    expect(style.color, BondTokens.fallback.muted);
  });

  testWidgets('urgent uses the danger wash; dashed paints a dash border', (t) async {
    await pumpBond(
      t,
      const Column(children: [
        BondListRow(title: 'Urgent', urgent: true),
        BondListRow(title: 'Tentative', dashed: true),
      ]),
    );
    final deco = t
        .widget<Container>(find
            .ancestor(of: find.text('Urgent'), matching: find.byType(Container))
            .first)
        .decoration! as BoxDecoration;
    expect(deco.color, BondTokens.fallback.danger.wash);
    expect(find.byType(CustomPaint), findsWidgets);
  });

  testWidgets('titleMaxLines lets a long title wrap; phone width holds', (t) async {
    await pumpBond(
      t,
      const BondListRow(
        title: 'A very long title that needs more than one line on a phone '
            'screen to be read in full',
        titleMaxLines: 3,
        leading: Icon(Icons.person),
        trailing: Text('Trail'),
      ),
    );
    expect(t.takeException(), isNull);
    // One line of 16 px text at 1.5 leading is 24 px tall; a wrapped title
    // is taller.
    expect(t.getSize(find.textContaining('A very long')).height, greaterThan(30));
  });
}
