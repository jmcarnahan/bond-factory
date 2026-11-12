import 'dart:async';

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_notify_ui/bond_notify_ui.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/pages/inbox_page.dart';

import 'todo_rig.dart';

class FakeAlert implements NoticeAlert {
  final List<String> shown = [];

  @override
  Future<bool> requestPermission() async => true;

  @override
  void show(Notice n) => shown.add(n.id);
}

Finder field(String id) => find.descendant(of: byId(id), matching: find.byType(TextField));

List<Map<String, Object?>> stages() => [
      noticeJson('n3', 'Send estimate is overdue', stage: 'past', seq: 1, last: true, createdAt: '2026-03-12T15:58:00Z'),
      noticeJson('n2', 'Send estimate is due', stage: 'due', createdAt: '2026-03-12T15:57:00Z'),
      noticeJson('n1', 'Send estimate is due soon', actions: ['done', 'snooze'], createdAt: '2026-03-12T15:56:00Z'),
    ];

TodoRig rig([List<Map<String, Object?>>? items]) {
  final list = items ?? stages();
  final r = TodoRig()..baseline(notices: list);
  r.on.json('POST', '/notices/n1/read', {...list.last, 'read_at': '2026-03-12T16:00:00Z'});
  r.on.json('POST', '/notices/n2/dismiss', {...list[1], 'dismissed_at': '2026-03-12T16:00:00Z'});
  r.on.json('POST', '/notices/read-all', {'unread_count': 0});
  return r;
}

int unread(WidgetTester t) => t.widget<BondNoticeBadge>(find.byType(BondNoticeBadge)).unread;

void main() {
  for (final phone in [false, true]) {
    final width = phone ? '390' : '1280';
    for (final mode in InboxFeedMode.values) {
      testWidgets('$width ${mode.name} feed: one notice per stage, the last one marked, read and dismiss persist', (t) async {
        final r = rig();
        final alert = FakeAlert();
        await pumpPage(t, InboxPage(services: r.services, mode: mode, alert: alert), phone: phone);
        expect(find.text('Feed: ${mode.name}'), findsOneWidget);
        for (final id in ['n1', 'n2', 'n3']) {
          expect(byId('sdk.inbox.list.row-$id'), findsWidgets, reason: id);
        }
        expect(find.text('Last reminder'), findsOneWidget);
        expect(unread(t), 3);
        expect(alert.shown, containsAll(['n1', 'n2', 'n3']), reason: 'fresh unread notices raise the alert');

        await t.tap(find.text('Send estimate is due soon'));
        await settle(t);
        expect(r.all('POST', '/notices/n1/read'), hasLength(1));
        expect(unread(t), 2);

        await t.tap(byId('sdk.inbox.list.row-n2-dismiss').first);
        await settle(t);
        expect(r.all('POST', '/notices/n2/dismiss'), hasLength(1));
        expect(byId('sdk.inbox.list.row-n2'), findsNothing);
        expect(unread(t), 1);

        await t.tap(byId('sdk.inbox.list.mark-all').first);
        await settle(t);
        expect(r.all('POST', '/notices/read-all'), hasLength(1));
        expect(unread(t), 0);
        await expectNoOverlays(t);
        expect(t.takeException(), isNull);
        await leave(t);
      });
    }
  }

  testWidgets('the switch shows the same notices through the other feed', (t) async {
    final r = rig();
    await pumpPage(t, InboxPage(services: r.services, alert: FakeAlert()));
    expect(find.text('Feed: polling'), findsOneWidget);
    await t.tap(byId('sdk.inbox.feed-watch').first);
    await settle(t, 12);
    expect(find.text('Feed: watch'), findsOneWidget);
    for (final id in ['n1', 'n2', 'n3']) {
      expect(byId('sdk.inbox.list.row-$id'), findsWidgets, reason: id);
    }
    await t.tap(byId('sdk.inbox.feed-polling').first);
    await settle(t, 12);
    expect(find.text('Feed: polling'), findsOneWidget);
    expect(byId('sdk.inbox.list.row-n3'), findsWidgets);
    await leave(t);
  });

  testWidgets('Done, Snooze and Cancel go through the act route; a non-owner row has no Cancel', (t) async {
    final r = rig();
    r.on.json('POST', '/notices/n2/act', {
      'notice': {...stages()[1], 'read_at': '2026-03-12T16:00:00Z'},
      'task': taskJson('t1', 'Send estimate', status: TaskStatus.done),
    });
    r.on.json('POST', '/notices/n3/act', {
      'notice': {...stages()[0], 'read_at': '2026-03-12T16:00:00Z'},
      'task': taskJson('t1', 'Send estimate'),
    });
    await pumpPage(t, InboxPage(services: r.services, alert: FakeAlert()));
    expect(byId('sdk.inbox.list.row-n2-cancel'), findsWidgets);
    expect(byId('sdk.inbox.list.row-n1-cancel'), findsNothing, reason: 'actions list has no cancel');
    expect(byId('sdk.inbox.list.row-n1-done'), findsWidgets);
    expect(byId('sdk.inbox.list.row-n1-snooze'), findsWidgets);

    await t.tap(byId('sdk.inbox.list.row-n2-done').first);
    await settle(t);
    expect((r.only('POST', '/notices/n2/act').json as Map)['action'], 'done');
    expect(byId('sdk.inbox.list.undo'), findsWidgets);

    await t.tap(byId('sdk.inbox.list.row-n3-snooze').first);
    await settle(t);
    expect((r.only('POST', '/notices/n3/act').json as Map)['action'], 'snooze');
    expect(find.textContaining('Snoozed'), findsWidgets);
    await leave(t);
  });

  testWidgets('a refused cancel (403) is worded inline', (t) async {
    final r = rig();
    r.on.json('POST', '/notices/n2/act', {
      'detail': {'code': 'not_task_owner', 'message': 'Only the owner can cancel this task'},
    }, status: 403);
    await pumpPage(t, InboxPage(services: r.services, alert: FakeAlert()));
    await t.tap(byId('sdk.inbox.list.row-n2-cancel').first);
    await settle(t);
    expect(byId('sdk.inbox.error'), findsWidgets);
    expect(find.text('Only the owner can cancel this task'), findsWidgets);
    await leave(t);
  });

  testWidgets('Tick runs the jobs and the next stage arrives as a new unread notice', (t) async {
    final first = [stages().last];
    final r = TodoRig()..baseline(notices: first);
    r.on.json('GET', '/notices', {'items': stages(), 'unread_count': 3});
    r.on.json('POST', '/jobs/tick', {'ran': <Object?>[]});
    r.on.json('PUT', '/fake/clock', {'now': '2026-03-12T16:00:00Z'});
    await pumpPage(t, InboxPage(services: r.services, alert: FakeAlert()));
    expect(unread(t), 1);
    await t.enterText(field('sdk.inbox.clock-now'), '2026-03-12T16:00:00Z');
    await t.tap(byId('sdk.inbox.clock-tick').first);
    await settle(t, 12);
    expect((r.only('PUT', '/fake/clock').json as Map)['now'], '2026-03-12T16:00:00.000Z');
    expect((r.only('POST', '/jobs/tick').json as Map)['now'], '2026-03-12T16:00:00.000Z');
    expect(unread(t), 3);
    expect(byId('sdk.inbox.list.row-n3'), findsWidgets);
    await leave(t);
  });

  testWidgets('quick switches during the sign-in leave one controller; no timer outlives the page', (t) async {
    final gate = Completer<void>();
    final r = TodoRig(ensureSignedIn: () async {
      await gate.future;
      return null;
    })
      ..baseline(notices: stages());
    await pumpPage(t, InboxPage(services: r.services, alert: FakeAlert(), pollEvery: const Duration(seconds: 1)));
    await t.tap(byId('sdk.inbox.feed-watch').first);
    await t.pump();
    await t.tap(byId('sdk.inbox.feed-polling').first);
    await t.pump();
    await t.tap(byId('sdk.inbox.feed-watch').first);
    await t.pump();
    gate.complete();
    await settle(t, 12);
    expect(find.text('Feed: watch'), findsOneWidget);
    // Three opens were asked for; only the last one built a feed, which asked for the notices once.
    expect(r.all('GET', '/notices'), hasLength(1));

    // The poll timer belongs to the one controller: it fires and refreshes (no more than one feed).
    await t.pump(const Duration(seconds: 1));
    await t.pump();
    expect(r.all('GET', '/notices'), hasLength(2));

    await leave(t);
    final after = r.all('GET', '/notices').length;
    await t.pump(const Duration(seconds: 3));
    expect(r.all('GET', '/notices'), hasLength(after), reason: 'no timer after dispose');
  });
}
