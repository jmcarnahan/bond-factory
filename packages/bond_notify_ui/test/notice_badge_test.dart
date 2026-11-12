import 'package:bond_notify_ui/bond_notify_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

Widget host(int unread) => BondNoticeBadge(
      unread: unread,
      semanticsId: 'b',
      child: const Padding(padding: EdgeInsets.all(8), child: Icon(Icons.notifications_none)),
    );

void main() {
  testWidgets('hidden at 0', (t) async {
    await atBothWidths(t, () => host(0), check: (_) async {
      expect(find.byIcon(Icons.notifications_none), findsOneWidget);
      expect(find.text('0'), findsNothing);
    });
  });

  testWidgets('shows 5', (t) async {
    await atBothWidths(t, () => host(5), check: (_) async {
      expect(find.text('5'), findsOneWidget);
    });
  });

  testWidgets('150 shows 99+ and announces the true count', (t) async {
    final h = t.ensureSemantics();
    await atBothWidths(t, () => host(150), check: (_) async {
      expect(find.text('99+'), findsOneWidget);
      expect(find.bySemanticsLabel('150 unread'), findsOneWidget);
      expect(byId('b'), findsOneWidget);
    });
    h.dispose();
  });

  testWidgets('99 shows 99, 1 announces 1 unread, no child works', (t) async {
    final h = t.ensureSemantics();
    await pumpAt(t, const BondNoticeBadge(unread: 99));
    expect(find.text('99'), findsOneWidget);
    await pumpAt(t, const BondNoticeBadge(unread: 1));
    expect(find.bySemanticsLabel('1 unread'), findsOneWidget);
    h.dispose();
  });
}
