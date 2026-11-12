import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_notifications/testing.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/todo/todo_alerts.dart';

import 'todo_rig.dart';

void main() {
  tearDown(TodoAlerts.stop);

  test('the coordinator starts once, schedules the stages of an open task and stops on sign-out', () async {
    final open = [
      taskJson('t1', 'Send estimate', date: '2026-03-13', time: '10:00', dueAt: DateTime.utc(2026, 3, 13, 17)),
    ];
    final r = TodoRig()..baseline(today: todayJson(today: open), open: open);
    final plugin = FakeAlertPlugin();

    await TodoAlerts.start(r.services, plugin: plugin);
    await TodoAlerts.start(r.services, plugin: plugin);
    expect(TodoAlerts.running, isTrue);
    expect(plugin.initialised, isTrue);
    expect(plugin.scheduled, isNotEmpty);
    expect(plugin.scheduled.map((s) => s.taskId).toSet(), {'t1'});
    // Lead 60 (the default): the close notice is an hour before the due instant, 17:00 UTC.
    final close = DateTime.utc(2026, 3, 13, 16);
    expect(plugin.scheduled.map((s) => s.atUtc), contains(close));
    expect(r.all('GET', '/tasks/settings'), hasLength(1), reason: 'the second start did nothing');

    TodoAlerts.updatePrefs(const TaskSettings(startOfDay: '07:00', endOfDay: '18:00', leadMinutes: 30));
    await pumpEventQueue();
    await TodoAlerts.settled;
    final times = plugin.scheduled.map((s) => s.atUtc).toList();
    expect(times, contains(DateTime.utc(2026, 3, 13, 16, 30)), reason: 'the close notice moved to 30 minutes before');
    expect(times, isNot(contains(close)));

    await TodoAlerts.stop();
    expect(TodoAlerts.running, isFalse);
    expect(plugin.scheduled, isEmpty, reason: 'sign-out cancels every local alert');
  });
}
