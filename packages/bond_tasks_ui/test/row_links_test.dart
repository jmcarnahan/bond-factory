import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

Task _t(int n) => Task(
      id: 'a',
      title: 'Call',
      dueDate: '2026-03-12',
      links: [for (var i = 0; i < n; i++) TaskLink(kind: 'contact', id: 'c$i', label: 'Person $i')],
    );

void main() {
  for (final phone in [false, true]) {
    testWidgets('links on a row (phone=$phone)', (t) async {
      final sem = t.ensureSemantics();
      final tapped = <String>[];
      await pumpAt(t, BondTaskRow(task: _t(2), semanticsId: 'r', onLinkTap: (l) => tapped.add(l.id)), phone: phone);
      expect(find.text('Person 0'), findsOneWidget);
      expect(find.text('Person 1'), findsOneWidget);
      expect(find.bySemanticsIdentifier('r-link-1'), findsOneWidget);
      await t.tap(find.text('Person 1'));
      expect(tapped, ['c1']);
      await pumpAt(t, BondTaskRow(task: _t(0)), phone: phone);
      expect(find.textContaining('Person'), findsNothing);
      await pumpAt(t, BondTaskRow(task: _t(5)), phone: phone);
      expect(find.textContaining('Person'), findsNWidgets(3));
      expect(find.text('+2'), findsOneWidget);
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
      sem.dispose();
    });
  }

  testWidgets('the lists pass links through', (t) async {
    await pumpAt(t, BondTaskList(tasks: [_t(1)], today: kToday));
    expect(find.text('Person 0'), findsOneWidget);
    await pumpAt(t, BondTodayList(today: TaskToday(today: [_t(1)]), now: DateTime(2026, 3, 12, 8)));
    expect(find.text('Person 0'), findsOneWidget);
  });

  for (final phone in [false, true]) {
    for (final links in [0, 2]) {
      testWidgets('a tap near the right edge of the body opens the task (links=$links, phone=$phone)', (t) async {
        var taps = 0;
        await pumpAt(t, BondTaskRow(task: _t(links), onTap: () => taps++), phone: phone);
        final box = t.getRect(find.byType(BondTaskRow));
        await t.tapAt(Offset(box.right - 8, t.getCenter(find.text('Call')).dy));
        expect(taps, 1);
      });
    }
  }
}
