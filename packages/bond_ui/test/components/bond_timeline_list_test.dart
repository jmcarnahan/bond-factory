import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/components/bond_timeline_list.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'kit_host.dart';

void main() {
  testWidgets('renders time, title and body; tone colours the dot', (t) async {
    setPhone(t);
    await pumpKit(
      t,
      const BondTimelineList(items: [
        BondTimelineItem(timeLabel: '9:00', title: 'Started'),
        BondTimelineItem(timeLabel: '10:30', title: 'Problem', body: 'Needs a look', tone: BondToneRole.danger),
      ]),
    );
    expect(find.text('9:00'), findsOneWidget);
    expect(find.text('Needs a look'), findsOneWidget);
    final row = find.byKey(const ValueKey('bond-timeline-1'));
    final dot = t.widget<Container>(
      find.descendant(of: row, matching: find.byWidgetPredicate((w) => w is Container && w.decoration is BoxDecoration && (w.decoration! as BoxDecoration).shape == BoxShape.circle)),
    );
    expect((dot.decoration! as BoxDecoration).color, BondTokens.fallback.danger.base);
    expect(t.takeException(), isNull);
    await expectNoOverlays(t);
  });
}
