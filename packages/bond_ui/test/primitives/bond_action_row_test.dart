import 'package:bond_ui/src/primitives/bond_action_row.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  testWidgets('renders title, context and action; the action fires', (t) async {
    final sem = t.ensureSemantics();
    var taps = 0;
    await pumpBond(
      t,
      BondActionRow(
        icon: Icons.mail_outline,
        title: 'Reply to the message',
        contextText: 'Received yesterday.',
        actionLabel: 'Reply',
        onAction: () => taps++,
        dueBadge: const Text('Due'),
        semanticsId: 'row-action',
      ),
    );
    expect(find.text('Reply to the message'), findsOneWidget);
    expect(find.text('Received yesterday.'), findsOneWidget);
    expect(find.text('Due'), findsOneWidget);
    expect(find.bySemanticsIdentifier('row-action'), findsOneWidget);
    await t.tap(find.text('Reply'));
    await t.pump();
    expect(taps, 1);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('expansion, result and error show under the row', (t) async {
    await pumpBond(
      t,
      const BondActionRow(
        icon: Icons.event,
        title: 'Schedule',
        iconTone: BondToneRole.caution,
        expansion: Text('Expanded content'),
        result: Text('Done line'),
        error: 'It failed',
      ),
    );
    expect(find.text('Expanded content'), findsOneWidget);
    expect(find.text('Done line'), findsOneWidget);
    expect(find.text('It failed'), findsOneWidget);
    final title = t.getTopLeft(find.text('Schedule'));
    expect(t.getTopLeft(find.text('Expanded content')).dy, greaterThan(title.dy));
    // Indented to the title.
    expect(t.getTopLeft(find.text('Expanded content')).dx,
        t.getTopLeft(find.text('Schedule')).dx);
  });

  testWidgets('trailing replaces the action button; busy shows progress', (t) async {
    await pumpBond(
      t,
      Column(children: [
        BondActionRow(
          icon: Icons.add,
          title: 'One',
          actionLabel: 'Hidden',
          onAction: () {},
          trailing: const Text('Custom trailing'),
        ),
        BondActionRow(
          icon: Icons.add,
          title: 'Two',
          actionLabel: 'Busy',
          busy: true,
          onAction: () {},
        ),
      ]),
    );
    expect(find.text('Custom trailing'), findsOneWidget);
    expect(find.text('Hidden'), findsNothing);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });
}
