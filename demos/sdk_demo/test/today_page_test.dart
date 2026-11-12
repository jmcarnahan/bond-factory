import 'dart:async';

import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/pages/today_page.dart';
import 'package:sdk_demo/src/todo/todo_alerts.dart';

import 'todo_rig.dart';

Map<String, Object?> due10(String id, {String owner = 'demo-user-1', String? assigned, bool overdue = false}) => taskJson(
      id,
      'Send estimate',
      date: '2026-03-12',
      time: '10:00',
      dueAt: DateTime.utc(2026, 3, 12, 17),
      owner: owner,
      assigned: assigned,
      overdue: overdue,
    );

Finder field(String id) => find.descendant(of: byId(id), matching: find.byType(TextField));

void main() {
  for (final phone in [false, true]) {
    final width = phone ? '390' : '1280';

    testWidgets('$width: create by hand with a priority and a contact link', (t) async {
      final r = TodoRig()..baseline();
      r.on.json('GET', '/tasks/links/search', {
        'items': [
          {'kind': 'contact', 'id': 'c1', 'label': 'Ann Example'},
        ],
      });
      r.on.json('POST', '/tasks', taskJson('n1', 'Call Ann', date: '2026-03-12', priority: TaskPriority.high), status: 201);
      // The second read of the day view (after the save) shows the new task.
      r.on.json('GET', '/tasks/today', todayJson(today: [taskJson('n1', 'Call Ann', date: '2026-03-12', priority: TaskPriority.high)]));
      await pumpPage(t, TodayPage(services: r.services), phone: phone);
      expect(r.only('GET', '/tasks/today').url.queryParameters['time_zone'], 'America/Los_Angeles');

      await t.enterText(field('sdk.today.form-title'), 'Call Ann');
      await t.tap(find.text('High'));
      await t.pump();
      await t.enterText(field('sdk.today.form-links'), 'an');
      await t.pump(const Duration(milliseconds: 400));
      await t.pump();
      await t.tap(find.text('Ann Example'));
      await t.pump();
      await t.tap(find.text('Save task'));
      await settle(t);

      final body = r.only('POST', '/tasks').json as Map;
      expect(body['title'], 'Call Ann');
      expect(body['priority'], 3);
      expect((body['links'] as List).single, containsPair('id', 'c1'));
      expect(body['time_zone'], 'America/Los_Angeles');
      expect(byId('sdk.today.row-n1'), findsWidgets);
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
      await leave(t);
    });

    testWidgets('$width: the stage banner follows close, due and past, and the section moves to overdue', (t) async {
      final r = TodoRig()..baseline(today: todayJson(today: [due10('t1')]));
      r.services.fakeNow.value = DateTime.utc(2026, 3, 12, 16, 30);
      final handle = t.ensureSemantics();
      await pumpPage(t, TodayPage(services: r.services), phone: phone);
      expect(find.text('Due soon'), findsOneWidget);
      expect(byId('sdk.today.task-t1.banner-done'), findsWidgets);
      expect(byId('sdk.today.task-t1.banner-snooze'), findsWidgets);
      expect(byId('sdk.today.task-t1.banner-cancel'), findsWidgets);
      expect(find.text('Today (1)'), findsOneWidget);

      r.services.fakeNow.value = DateTime.utc(2026, 3, 12, 17, 5);
      await settle(t);
      expect(find.text('Due now'), findsOneWidget);

      r.services.fakeNow.value = DateTime.utc(2026, 3, 12, 17, 40);
      await settle(t);
      expect(find.text('Overdue'), findsWidgets);
      expect(find.text('Overdue (1)'), findsOneWidget);
      expect(find.text('Today (1)'), findsNothing);
      await expectNoOverlays(t);
      handle.dispose();
      await leave(t);
    });
  }

  testWidgets('a banner for a task the person does not own has no Cancel', (t) async {
    final r = TodoRig()..baseline(today: todayJson(today: [due10('t2', owner: 'demo-user-2', assigned: 'demo-user-1')]));
    r.services.fakeNow.value = DateTime.utc(2026, 3, 12, 16, 30);
    await pumpPage(t, TodayPage(services: r.services));
    expect(byId('sdk.today.task-t2.banner-done'), findsWidgets);
    expect(byId('sdk.today.task-t2.banner-cancel'), findsNothing);
    await leave(t);
  });

  testWidgets('Done leaves the list at once and Undo reopens it; Snooze hides the banner', (t) async {
    final open = [due10('t1'), taskJson('t3', 'Other', date: '2026-03-12')];
    final r = TodoRig()..baseline(today: todayJson(today: open), open: open);
    r.services.fakeNow.value = DateTime.utc(2026, 3, 12, 16, 30);
    r.on.json('POST', '/tasks/t1/complete', taskJson('t1', 'Send estimate', status: TaskStatus.done));
    r.on.json('POST', '/tasks/t1/reopen', due10('t1'));
    await pumpPage(t, TodayPage(services: r.services));
    await t.tap(byId('sdk.today.task-t1.banner-snooze').first);
    await settle(t);
    expect(find.text('Due soon'), findsNothing);

    final gate = r.holds['POST /tasks/t1/complete'] = Completer<void>();
    await t.tap(byId('sdk.today.complete-t1').first);
    await settle(t);
    // Optimistic: it left the list while the server had not answered.
    expect(r.all('POST', '/tasks/t1/complete'), isEmpty);
    expect(byId('sdk.today.row-t1'), findsNothing);
    expect(byId('sdk.today.undo'), findsWidgets);
    gate.complete();
    await settle(t);
    expect(r.all('POST', '/tasks/t1/complete'), hasLength(1));

    await t.tap(byId('sdk.today.undo').first);
    await settle(t);
    expect(r.all('POST', '/tasks/t1/reopen'), hasLength(1));
    expect(byId('sdk.today.row-t1'), findsWidgets);
    await leave(t);
  });

  testWidgets('Cancel on the banner posts to the cancel route', (t) async {
    final r = TodoRig()..baseline(today: todayJson(today: [due10('t1')]));
    r.services.fakeNow.value = DateTime.utc(2026, 3, 12, 16, 30);
    r.on.json('POST', '/tasks/t1/cancel', taskJson('t1', 'Send estimate', status: TaskStatus.cancelled));
    await pumpPage(t, TodayPage(services: r.services));
    await t.tap(byId('sdk.today.task-t1.banner-cancel').first);
    await settle(t);
    expect(r.all('POST', '/tasks/t1/cancel'), hasLength(1));
    await leave(t);
  });

  testWidgets('the fake clock Tick runs the jobs and a task due at a time moves from today to overdue', (t) async {
    final r = TodoRig()..baseline(today: todayJson(today: [due10('t1')]));
    r.on.json('POST', '/jobs/tick', {'ran': <Object?>[]});
    r.on.json('PUT', '/fake/clock', {'now': '2026-03-12T18:00:00Z'});
    // The read after the tick: the server now lists it as overdue.
    r.on.json('GET', '/tasks/today', todayJson(overdue: [due10('t1', overdue: true)]));
    await pumpPage(t, TodayPage(services: r.services));
    expect(find.text('Today (1)'), findsOneWidget);
    expect(find.text('Overdue (1)'), findsNothing);

    await t.enterText(field('sdk.today.clock-now'), '2026-03-12T18:00:00Z');
    await t.tap(byId('sdk.today.clock-tick').first);
    await settle(t);
    expect((r.only('PUT', '/fake/clock').json as Map)['now'], '2026-03-12T18:00:00.000Z');
    expect((r.only('POST', '/jobs/tick').json as Map)['now'], '2026-03-12T18:00:00.000Z');
    expect(find.text('Overdue (1)'), findsOneWidget);
    expect(find.text('Today (1)'), findsNothing);
    await leave(t);
  });

  testWidgets('a clock field that is not an instant is refused inline', (t) async {
    final r = TodoRig()..baseline();
    await pumpPage(t, TodayPage(services: r.services));
    await t.enterText(field('sdk.today.clock-now'), 'tomorrow');
    await t.tap(byId('sdk.today.clock-tick').first);
    await settle(t);
    expect(byId('sdk.today.clock-error'), findsWidgets);
    expect(r.all('POST', '/jobs/tick'), isEmpty);
    await leave(t);
  });

  testWidgets('the page reads the pinned clock on load, and Real time un-pins it', (t) async {
    final r = TodoRig()..baseline(today: todayJson(today: [due10('t1')]));
    r.on.json('GET', '/fake/clock', {'now': '2026-03-12T17:40:00Z'});
    r.on.json('PUT', '/fake/clock', {'now': null});
    await pumpPage(t, TodayPage(services: r.services));
    expect(r.services.fakeNow.value, DateTime.utc(2026, 3, 12, 17, 40));
    expect(find.text('Overdue (1)'), findsOneWidget);

    await t.tap(byId('sdk.today.clock-real').first);
    await settle(t);
    expect((r.only('PUT', '/fake/clock').json as Map)['now'], isNull);
    expect(r.services.fakeNow.value, isNull);
    expect(r.all('POST', '/jobs/tick'), isEmpty);
    await leave(t);
  });

  testWidgets('a banner action goes through the notice act route when the inbox holds that notice', (t) async {
    final r = TodoRig()
      ..baseline(
        today: todayJson(today: [due10('t1')]),
        notices: [noticeJson('n9', 'Send estimate is due soon', taskId: 't1', stage: 'close')],
      );
    r.services.fakeNow.value = DateTime.utc(2026, 3, 12, 16, 30);
    r.on.json('POST', '/notices/n9/act', {
      'notice': noticeJson('n9', 'Send estimate is due soon', taskId: 't1', readAt: '2026-03-12T16:30:00Z'),
      'task': taskJson('t1', 'Send estimate', status: TaskStatus.done),
    });
    await pumpPage(t, TodayPage(services: r.services));
    await t.tap(byId('sdk.today.task-t1.banner-done').first);
    await settle(t);
    expect((r.only('POST', '/notices/n9/act').json as Map)['action'], 'done');
    expect(r.all('POST', '/tasks/t1/complete'), isEmpty, reason: 'the act route completes the task');
    await leave(t);
  });

  testWidgets('a tap on a notification is shown on the Today page', (t) async {
    final handle = t.ensureSemantics();
    final r = TodoRig()..baseline(today: todayJson(today: [due10('t1')]));
    TodoAlerts.open('/tasks/t1');
    addTearDown(() => TodoAlerts.openedTask.value = null);
    await pumpPage(t, TodayPage(services: r.services));
    expect(labelOf(t, 'sdk.today.opened'), 'Opened from a notification: Send estimate');
    await t.tap(byId('sdk.today.opened-dismiss').first);
    await settle(t);
    expect(byId('sdk.today.opened'), findsNothing);
    handle.dispose();
    await leave(t);
  });

  testWidgets('a tick that fails after the pin shows the error and the server\'s pinned clock', (t) async {
    final r = TodoRig()..baseline(today: todayJson(today: [due10('t1')]));
    r.on.json('PUT', '/fake/clock', {'now': '2026-03-12T18:00:00Z'});
    r.canned.responses.fail('POST', '/jobs/tick', const SocketLikeError());
    // First read of the clock (page load): not pinned. Second (after the failed tick): pinned.
    r.on.json('GET', '/fake/clock', {'now': null});
    r.on.json('GET', '/fake/clock', {'now': '2026-03-12T18:00:00Z'});
    await pumpPage(t, TodayPage(services: r.services));
    expect(r.services.fakeNow.value, isNull);

    await t.enterText(field('sdk.today.clock-now'), '2026-03-12T18:00:00Z');
    await t.tap(byId('sdk.today.clock-tick').first);
    await settle(t);
    expect(byId('sdk.today.clock-error'), findsWidgets);
    expect(r.services.fakeNow.value, DateTime.utc(2026, 3, 12, 18));
    expect(t.takeException(), isNull);
    await leave(t);
  });
}

class SocketLikeError implements Exception {
  const SocketLikeError();

  @override
  String toString() => 'connection lost';
}
