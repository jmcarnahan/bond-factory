import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/pages/capture_page.dart';

import 'todo_rig.dart';

Finder field(String id) => find.descendant(of: byId(id), matching: find.byType(TextField));

Map<String, Object?> taskItem(String title, {String? date, int? priority, List<Object?> links = const []}) => {
      'kind': 'task',
      'title': title,
      'due_date': date,
      'due_time': null,
      'due_defaulted': false,
      'priority': priority,
      'links': links,
      'confidence': 0.9,
      'flags': <Object?>[],
      'degraded': false,
    };

Map<String, Object?> eventItem(String title) => {
      'kind': 'event',
      'title': title,
      'start_date': '2026-03-13',
      'start_time': '14:00',
      'all_day': false,
      'end_date': null,
      'end_time': '15:00',
      'links': <Object?>[],
      'confidence': 0.9,
      'flags': <Object?>[],
      'degraded': false,
    };

TodoRig rig(Map<String, Object?> parse) {
  final r = TodoRig()..baseline();
  r.on.json('POST', '/tasks/parse', parse);
  r.on.json('POST', '/tasks', taskJson('n1', 'x'), status: 201);
  r.on.json('POST', '/capture/events', {'id': 'e1'}, status: 201);
  return r;
}

Future<void> parseIt(WidgetTester t, TodoRig r, {bool phone = false}) async {
  await pumpPage(t, CapturePage(services: r.services), phone: phone);
  await t.enterText(field('sdk.capture.text'), 'Call Ann tomorrow, email the estimate, lunch with Bo at 2');
  await t.tap(byId('sdk.capture.parse').first);
  await settle(t);
}

void main() {
  for (final phone in [false, true]) {
    final width = phone ? '390' : '1280';

    testWidgets('$width: three drafts, accept creates two tasks and sends one event', (t) async {
      final r = rig({
        'items': [
          taskItem('Call Ann', date: '2026-03-13', links: [
            {
              'text': 'Ann',
              'kind': 'contact',
              'candidates': [
                {'id': 'c1', 'label': 'Ann Example'},
              ],
            },
          ]),
          taskItem('Email the estimate', date: '2026-03-13', priority: 3),
          eventItem('Lunch with Bo'),
        ],
        'degraded': false,
        'reason': null,
      });
      await parseIt(t, r, phone: phone);
      final parseBody = r.only('POST', '/tasks/parse').json as Map;
      expect(parseBody.containsKey('today'), isFalse, reason: 'the server ignores today');
      expect(parseBody['time_zone'], 'America/Los_Angeles');
      for (var n = 0; n < 3; n++) {
        expect(byId('sdk.capture.review-item-$n-title'), findsWidgets, reason: 'draft $n');
      }
      expect(r.all('POST', '/tasks'), isEmpty, reason: 'parsing creates nothing');

      await t.tap(byId('sdk.capture.review-accept').first);
      await settle(t);
      final created = r.all('POST', '/tasks');
      expect(created, hasLength(2));
      expect((created[0].json as Map)['title'], 'Call Ann');
      expect((created[0].json as Map)['source'], 'capture');
      expect(((created[0].json as Map)['links'] as List).single, containsPair('id', 'c1'));
      expect((created[1].json as Map)['priority'], 3);
      expect(r.all('POST', '/capture/events'), hasLength(1));
      expect((r.only('POST', '/capture/events').json as Map)['title'], 'Lunch with Bo');
      expect(labelOf0(t), 'Created 2 tasks and sent 1 event');
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
      await leave(t);
    });
  }

  testWidgets('a task flipped to an event is sent as an event', (t) async {
    final r = rig({
      'items': [taskItem('Call Ann', date: '2026-03-13'), taskItem('Email the estimate', date: '2026-03-13')],
      'degraded': false,
      'reason': null,
    });
    await parseIt(t, r);
    await t.tap(byId('sdk.capture.review-item-1-kind-event').first);
    await settle(t);
    await t.tap(byId('sdk.capture.review-accept').first);
    await settle(t);
    expect(r.all('POST', '/tasks'), hasLength(1));
    expect(r.all('POST', '/capture/events'), hasLength(1));
    expect((r.only('POST', '/capture/events').json as Map)['title'], 'Email the estimate');
    expect(r.services.events.value, hasLength(1));
    await leave(t);
  });

  testWidgets('a degraded parse shows one draft with the notice and the dropped count', (t) async {
    final r = rig({
      'items': [
        {...taskItem('Call Ann then email the estimate'), 'degraded': true},
      ],
      'degraded': true,
      'reason': 'model_unavailable',
      'dropped': 2,
    });
    await parseIt(t, r);
    expect(byId('sdk.capture.review-item-0-title'), findsWidgets);
    expect(byId('sdk.capture.review-item-1-title'), findsNothing);
    expect(byId('sdk.capture.review-notice'), findsWidgets);
    expect(find.text('2 items could not be read.'), findsOneWidget);
    await leave(t);
  });

  testWidgets('the fake-mode switch turns the model off and a degraded draft comes back', (t) async {
    final r = rig({
      'items': [
        {...taskItem('Call Ann and email the estimate'), 'degraded': true},
      ],
      'degraded': true,
      'reason': 'model_unavailable',
    });
    r.on.json('PUT', '/fake/capture', {'down': true});
    await pumpPage(t, CapturePage(services: r.services));
    await t.tap(byId('sdk.capture.model-off').first);
    await settle(t);
    expect(r.only('PUT', '/fake/capture').json, {'down': true});
    await t.enterText(field('sdk.capture.text'), 'Call Ann and email the estimate');
    await t.tap(byId('sdk.capture.parse').first);
    await settle(t);
    expect(byId('sdk.capture.review-notice'), findsWidgets);
    expect(byId('sdk.capture.review-item-1-title'), findsNothing);
    await leave(t);
  });

  testWidgets('discard throws the drafts away and creates nothing', (t) async {
    final r = rig({'items': [taskItem('Call Ann')], 'degraded': false, 'reason': null});
    await parseIt(t, r);
    await t.tap(byId('sdk.capture.review-discard').first);
    await settle(t);
    expect(byId('sdk.capture.review-item-0-title'), findsNothing);
    expect(r.all('POST', '/tasks'), isEmpty);
    await leave(t);
  });

  testWidgets('a refused parse (429) is worded inline', (t) async {
    final r = TodoRig()..baseline();
    r.on.json('POST', '/tasks/parse', {
      'detail': {'code': 'capture_denied', 'message': 'Too many requests. Try again in a minute.'},
    }, status: 429);
    await parseIt(t, r);
    expect(byId('sdk.capture.error'), findsWidgets);
    expect(find.textContaining('Too many requests'), findsWidgets);
    await leave(t);
  });
}

String labelOf0(WidgetTester t) => t.getSemantics(byId('sdk.capture.result').first).label;
