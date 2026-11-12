import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/pages/todo_calendar_page.dart';

import 'todo_rig.dart';

String markerLabel(String day) =>
    (find.byWidgetPredicate((w) => w is Semantics && w.properties.identifier == 'sdk.calendar.marker-$day').evaluate().first.widget
            as Semantics)
        .properties
        .label!;

TodoRig rig() {
  final r = TodoRig();
  final items = [
    taskJson('t1', 'Send estimate', date: '2026-03-12', time: '10:00', dueAt: DateTime.utc(2026, 3, 12, 17)),
    taskJson('t2', 'File report', date: '2026-03-12', dueAt: DateTime.utc(2026, 3, 13)),
    taskJson('t3', 'Later job', date: '2026-03-20', dueAt: DateTime.utc(2026, 3, 21)),
  ];
  r.baseline(open: items);
  return r;
}

void main() {
  for (final phone in [false, true]) {
    final width = phone ? '390' : '1280';

    testWidgets('$width: the lane lists the day and the month cells carry markers', (t) async {
      final r = rig();
      await pumpPage(t, TodoCalendarPage(services: r.services), phone: phone);
      expect(byId('sdk.calendar.row-t1'), findsWidgets);
      expect(byId('sdk.calendar.row-t2'), findsWidgets);
      expect(byId('sdk.calendar.row-t3'), findsNothing);
      expect(markerLabel('2026-03-12'), '2 due');
      expect(markerLabel('2026-03-20'), '1 due');

      await t.tap(find.text('20'));
      await settle(t);
      expect(byId('sdk.calendar.row-t3'), findsWidgets);
      expect(byId('sdk.calendar.row-t1'), findsNothing);
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
      await leave(t);
    });
  }

  testWidgets('past its time the marker and the lane say overdue; an event says Missed, never overdue', (t) async {
    final r = rig();
    r.on.json('GET', '/capture/events', {
      'items': [
        {'title': 'Lunch with Bo', 'start_date': '2026-03-12', 'start_time': '14:00', 'all_day': false},
      ],
    });
    await pumpPage(t, TodoCalendarPage(services: r.services));
    expect(markerLabel('2026-03-12'), '2 due');
    expect(find.textContaining('Missed'), findsNothing);

    // 2026-03-12 17:30 UTC is 10:30 local: t1 is past its time, the event (14:00) is not yet.
    r.services.fakeNow.value = DateTime.utc(2026, 3, 12, 17, 30);
    await settle(t);
    expect(markerLabel('2026-03-12'), '2 overdue');
    expect(find.textContaining('Missed'), findsNothing);

    // 22:00 UTC is 15:00 local: the event started an hour ago.
    r.services.fakeNow.value = DateTime.utc(2026, 3, 12, 22);
    await settle(t);
    final event = t.widget<Text>(find.textContaining('Lunch with Bo')).data!;
    expect(event, contains('Missed'));
    expect(event.toLowerCase(), isNot(contains('overdue')));
    await leave(t);
  });

  testWidgets('the selected day and the lane follow the server\'s pinned clock', (t) async {
    final r = rig();
    r.on.json('GET', '/fake/clock', {'now': '2026-03-20T16:00:00Z'});
    await pumpPage(t, TodoCalendarPage(services: r.services));
    final state = (find.byWidgetPredicate((w) => w is Semantics && w.properties.identifier == 'sdk.calendar.clock-state')
            .evaluate()
            .first
            .widget as Semantics)
        .properties
        .label!;
    expect(state, contains('2026-03-20'));
    expect(byId('sdk.calendar.row-t3'), findsWidgets, reason: 'the lane shows the pinned day without a tap');
    expect(byId('sdk.calendar.row-t1'), findsNothing);
    await leave(t);
  });
}
