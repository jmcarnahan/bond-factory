import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/pages/todo_settings_page.dart';

import 'todo_rig.dart';

Finder field(String id) => find.descendant(of: byId(id), matching: find.byType(TextField));

Map<String, Object?> settingsJson({String end = '17:00', String zone = 'America/Los_Angeles', List<String> warnings = const []}) => {
      'time_zone': zone,
      'start_of_day': '08:00',
      'end_of_day': end,
      'lead_minutes': 60,
      'warnings': warnings,
    };

void main() {
  for (final phone in [false, true]) {
    final width = phone ? '390' : '1280';

    testWidgets('$width: moving the end of the work day saves it and restates the quiet hours', (t) async {
      final r = TodoRig()..baseline();
      r.on.json('PUT', '/tasks/settings', settingsJson(end: '18:00', warnings: ['2 date-only TODOs now fall due at 18:00']));
      await pumpPage(t, TodoSettingsPage(services: r.services), phone: phone);
      expect(find.textContaining('from 17:00 to 08:00'), findsOneWidget);

      await t.enterText(field('sdk.todo.settings-end'), '18:00');
      await t.tap(byId('sdk.todo.settings-save').first);
      await settle(t);

      expect((r.only('PUT', '/tasks/settings').json as Map)['end_of_day'], '18:00');
      expect(find.textContaining('from 18:00 to 08:00'), findsOneWidget);
      expect(find.text('2 date-only TODOs now fall due at 18:00'), findsOneWidget);
      expect(byId('sdk.todo.saved'), findsWidgets);
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
      await leave(t);
    });
  }

  testWidgets('choosing a zone sends it with the save and the pages use it afterwards', (t) async {
    final r = TodoRig()..baseline();
    r.on.json('PUT', '/tasks/settings', settingsJson(zone: 'America/Chicago'));
    await pumpPage(t, TodoSettingsPage(services: r.services));
    await t.enterText(field('sdk.todo.settings-zone'), 'Chicago');
    await t.pump(const Duration(milliseconds: 400));
    await t.pump();
    await t.tap(find.text('America/Chicago'));
    await t.pump();
    await t.tap(byId('sdk.todo.settings-save').first);
    await settle(t);
    expect((r.only('PUT', '/tasks/settings').json as Map)['time_zone'], 'America/Chicago');
    expect(r.services.zone, 'America/Chicago');
    expect(find.text('Zone: America/Chicago'), findsOneWidget);
    await leave(t);
  });

  testWidgets('a refused time is worded inline and nothing is sent', (t) async {
    final r = TodoRig()..baseline();
    await pumpPage(t, TodoSettingsPage(services: r.services));
    await t.enterText(field('sdk.todo.settings-end'), '25:99');
    await t.tap(byId('sdk.todo.settings-save').first);
    await settle(t);
    expect(r.all('PUT', '/tasks/settings'), isEmpty);
    expect(find.textContaining('HH:MM'), findsWidgets);
    await leave(t);
  });

  testWidgets('a server error shows inline', (t) async {
    final r = TodoRig();
    r.on.json('GET', '/tasks/settings', {
      'detail': {'code': 'db_unavailable', 'message': 'Database is down'},
    }, status: 503);
    await pumpPage(t, TodoSettingsPage(services: r.services));
    expect(find.text('Database is down'), findsWidgets);
    await leave(t);
  });
}
