import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_notifications/bond_tasks_notifications.dart';
import 'package:bond_tasks_notifications/testing.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('AlertTap payload round-trips and rejects junk', () {
    const tap = AlertTap(noticeId: 'n1', taskId: 't1', route: '/tasks/t1');
    final back = AlertTap.fromPayload(tap.toPayload());
    expect(back?.noticeId, 'n1');
    expect(back?.taskId, 't1');
    expect(back?.route, '/tasks/t1');
    expect(AlertTap.fromPayload(null), isNull);
    expect(AlertTap.fromPayload('nope'), isNull);
    expect(AlertTap.fromPayload('{"notice_id":1}'), isNull);
  });

  test('FakeAlertPlugin records and fires taps', () async {
    final fake = FakeAlertPlugin();
    AlertTap? got;
    await fake.init(onTap: (t) => got = t);
    final r = AlertRequest(
      id: 1,
      noticeId: 'n',
      taskId: 't',
      title: 'x',
      body: 'y',
      atUtc: DateTime.utc(2026, 1, 1),
      actions: const [NoticeAction.done],
    );
    await fake.schedule(r);
    await fake.show(r);
    expect((await fake.pending()).single.id, 1);
    await fake.cancel(1);
    expect(fake.cancelled, [1]);
    expect(await fake.pending(), isEmpty);
    fake.fireTap(const AlertTap(noticeId: 'n', taskId: 't', action: NoticeAction.snooze));
    expect(got?.action, NoticeAction.snooze);
    expect(fake.shown, hasLength(1));
    expect(await fake.requestPermission(), isTrue);
    expect(await fake.launchTap(), isNull);
  });

  test('shell names exist', () {
    expect(FlutterLocalAlertPlugin.new, isA<Function>());
    expect(FlutterTimeZoneSource.new, isA<Function>());
    expect(LocalTaskAlerts.new, isA<Function>());
    expect(NoticeActionHandler.new, isA<Function>());
    expect(TaskAlertsCoordinator.new, isA<Function>());
    expect(const PendingAlert(id: 1).payload, isNull);
    expect(const AlertLabels().titleFor('due'), 'Due now');
  });
}
