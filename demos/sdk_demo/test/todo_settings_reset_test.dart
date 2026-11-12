import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/pages/todo_settings_page.dart';

import 'todo_rig.dart';

Map<String, Object?> body({String end = '17:00', List<String> overridden = const []}) => {
      'time_zone': 'America/Los_Angeles',
      'start_of_day': '08:00',
      'end_of_day': end,
      'lead_minutes': 60,
      'warnings': <Object?>[],
      'overridden': overridden,
    };

void main() {
  testWidgets('a set field shows Reset to default; a reset sends null, the page reads again and the control goes', (t) async {
    final r = TodoRig();
    // Two reads before the reset (the zone report and the page load), then the server's answer after it.
    r.on.json('GET', '/tasks/settings', body(end: '18:30', overridden: ['end_of_day']));
    r.on.json('GET', '/tasks/settings', body(end: '18:30', overridden: ['end_of_day']));
    r.on.json('GET', '/tasks/settings', body());
    r.on.json('PUT', '/tasks/settings', body());
    await pumpPage(t, TodoSettingsPage(services: r.services));

    expect(byId('sdk.todo.settings-reset-end'), findsWidgets, reason: 'end_of_day is overridden');
    expect(byId('sdk.todo.settings-reset-start'), findsNothing, reason: 'start_of_day follows the app default');
    final reads = r.all('GET', '/tasks/settings').length;

    await t.tap(byId('sdk.todo.settings-reset-end').first);
    await settle(t);

    expect(r.only('PUT', '/tasks/settings').json, {'end_of_day': null});
    expect(r.all('GET', '/tasks/settings'), hasLength(reads + 1), reason: 'the page reads the settings again');
    expect(byId('sdk.todo.settings-reset-end'), findsNothing);
    expect(find.text('Settings saved'), findsOneWidget);
    await expectNoOverlays(t);
    expect(t.takeException(), isNull);
    await leave(t);
  });
}
