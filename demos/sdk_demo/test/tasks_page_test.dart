import 'package:bond_api/bond_api.dart';
import 'package:bond_auth/bond_auth.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/pages/tasks_page.dart';

Finder byId(String id) => find.byWidgetPredicate((w) => w is Semantics && w.properties.identifier == id);

String textOf(WidgetTester t, String id) =>
    t.widget<Text>(find.descendant(of: byId(id), matching: find.byType(Text))).data!;

Map<String, Object?> task(
  String id,
  String title, {
  String? date,
  String? time,
  TaskStatus status = TaskStatus.open,
  List<ChecklistItem> checklist = const [],
  String? provider,
  String? eventId,
  bool mirror = true,
}) =>
    Task(
      id: id,
      title: title,
      dueDate: date,
      dueTime: time,
      status: status,
      checklist: checklist,
      externalProvider: provider,
      externalEventId: eventId,
      mirrorEnabled: mirror,
      mirrorStatus: provider == null ? MirrorStatus.pending : MirrorStatus.mirrored,
    ).toJson();

class TasksRig {
  TasksRig(List<Object?> lists) {
    for (final l in lists) {
      canned.responses.json('GET', '/tasks', {'items': l, 'total': (l as List).length});
    }
    canned.responses.json('GET', '/tasks/summary', {'open': 2, 'overdue': 0, 'due_today': 1, 'no_date': 0});
    api = TasksApi(ApiClient(baseUrl: Uri.parse('http://example.test'), http: canned));
    jobs = DemoJobsApi(ApiClient(baseUrl: Uri.parse('http://example.test'), http: canned));
  }

  final CannedHttpClient canned = CannedHttpClient();
  late final TasksApi api;
  late final DemoJobsApi jobs;

  Widget page() => TasksPage(
        api: api,
        jobs: jobs,
        ensureSignedIn: () async => null,
        clock: () => DateTime(2026, 3, 12, 8),
      );

  RecordedRequest only(String method, String path) => canned.requestsTo(method, path).single;
}

Future<void> pumpPage(WidgetTester t, TasksRig r, {bool phone = false}) async {
  final size = phone ? const Size(390, 3600) : const Size(900, 3600);
  if (phone) {
    setPhone(t, size: size);
  } else {
    setWideScreen(t, size: size);
  }
  await pumpApp(t, r.page());
  await pumpUntil(t, find.text('Tasks'));
  for (var i = 0; i < 5; i++) {
    await t.pump(const Duration(milliseconds: 20));
  }
}

Future<void> settle(WidgetTester t) async {
  for (var i = 0; i < 6; i++) {
    await t.pump(const Duration(milliseconds: 20));
  }
}

void main() {
  testWidgets('the list renders rows in sections with the summary', (t) async {
    final r = TasksRig([
      [
        task('a', 'Send estimate', date: '2026-03-12', time: '09:30'),
        task('b', 'Someday'),
        task('c', 'Filed', date: '2026-03-10', status: TaskStatus.done),
      ],
    ]);
    await pumpPage(t, r);
    expect(byId('sdk.tasks.row-a'), findsWidgets);
    expect(byId('sdk.tasks.row-b'), findsWidgets);
    expect(find.text('Today (1)'), findsOneWidget);
    expect(find.text('No date (1)'), findsOneWidget);
    expect(find.text('Done (1)'), findsOneWidget);
    expect(r.only('GET', '/tasks').url.queryParameters['today'], '2026-03-12');
    await expectNoOverlays(t);
  });

  testWidgets('quick add creates a task and the list reloads', (t) async {
    final r = TasksRig([
      <Object?>[],
      [task('n1', 'Buy tape')],
    ]);
    r.canned.responses.json('POST', '/tasks', task('n1', 'Buy tape'), status: 201);
    await pumpPage(t, r);
    expect(find.text('No tasks'), findsOneWidget);
    await t.enterText(find.descendant(of: byId('sdk.tasks.quick-add'), matching: find.byType(TextField)), 'Buy tape');
    await t.testTextInput.receiveAction(TextInputAction.done);
    await settle(t);
    expect((r.only('POST', '/tasks').json as Map)['title'], 'Buy tape');
    expect(byId('sdk.tasks.row-n1'), findsWidgets);
  });

  testWidgets('the full form creates a task with its fields', (t) async {
    final r = TasksRig([<Object?>[]]);
    r.canned.responses.json('POST', '/tasks', task('n2', 'From form'), status: 201);
    await pumpPage(t, r);
    final title = find.descendant(of: byId('sdk.tasks.form-title'), matching: find.byType(TextField));
    await t.ensureVisible(title);
    await t.enterText(title, 'From form');
    await t.ensureVisible(find.text('Save task'));
    await t.tap(find.text('Save task'));
    await settle(t);
    final body = r.only('POST', '/tasks').json as Map;
    expect(body['title'], 'From form');
    expect(body['mirror_enabled'], isTrue);
    expect(body['remind_minutes_before'], kRemindNone);
  });

  testWidgets('complete posts to the complete route', (t) async {
    final r = TasksRig([
      [task('a', 'Open one', date: '2026-03-12')],
    ]);
    r.canned.responses.json('POST', '/tasks/a/complete', task('a', 'Open one', status: TaskStatus.done));
    await pumpPage(t, r);
    await t.tap(find.byIcon(Icons.radio_button_unchecked));
    await settle(t);
    expect(r.canned.requestsTo('POST', '/tasks/a/complete'), hasLength(1));
  });

  testWidgets('a checklist tick puts done on the line', (t) async {
    final r = TasksRig([
      [
        task('a', 'With list', checklist: const [ChecklistItem(id: 'x', text: 'First'), ChecklistItem(id: 'y', text: 'Second')]),
      ],
    ]);
    r.canned.responses.json('PUT', '/tasks/a/checklist/y', task('a', 'With list'));
    await pumpPage(t, r);
    await t.tap(find.text('Second'));
    await settle(t);
    expect(r.only('PUT', '/tasks/a/checklist/y').json, {'done': true});
    expect(byId('sdk.tasks.check-a-1'), findsWidgets);
  });

  testWidgets('delete asks twice, then deletes', (t) async {
    final r = TasksRig([
      [task('a', 'Doomed')],
    ]);
    r.canned.responses.on('DELETE', '/tasks/a', const CannedResponse(204));
    await pumpPage(t, r);
    await t.tap(find.byIcon(Icons.delete_outline));
    await t.pump();
    expect(r.canned.requestsTo('DELETE', '/tasks/a'), isEmpty);
    await t.tap(find.text('Confirm'));
    await settle(t);
    expect(r.canned.requestsTo('DELETE', '/tasks/a'), hasLength(1));
    await t.pump(const Duration(seconds: 11));
  });

  testWidgets('run due jobs ticks at the latest due time plus two minutes and lists the notice', (t) async {
    final r = TasksRig([
      [
        task('a', 'Early', date: '2026-03-12', time: '09:30'),
        task('b', 'Late', date: '2026-03-14', time: '16:00'),
        task('c', 'Done later', date: '2026-04-01', status: TaskStatus.done),
        task('d', 'No date'),
      ],
    ]);
    r.canned.responses.json('POST', '/jobs/tick', {
      'ran': [
        {'id': 'job-1', 'job_type': 'task_reminder', 'status': 'done'},
      ],
    });
    r.canned.responses.json('GET', '/tasks/notices', {
      'items': [
        {'task_id': 'b', 'title': 'Late'},
      ],
    });
    await pumpPage(t, r);
    await t.ensureVisible(byId('sdk.tasks.run-due-jobs'));
    await t.tap(byId('sdk.tasks.run-due-jobs'));
    await settle(t);
    expect((r.only('POST', '/jobs/tick').json as Map)['now'], '2026-03-14T16:02:00.000Z');
    expect(textOf(t, 'sdk.tasks.notice-0'), 'Late (b)');
  });

  testWidgets('the mirror result shows provider and external id', (t) async {
    final r = TasksRig([
      [task('a', 'Mirrored', date: '2026-03-12', provider: 'google', eventId: 'evt-77')],
    ]);
    await pumpPage(t, r);
    expect(textOf(t, 'sdk.tasks.external-a'), 'Calendar: google evt-77');
  });

  testWidgets('a load failure shows the error with a retry', (t) async {
    final r = TasksRig([]);
    r.canned.responses.json('GET', '/tasks', {'detail': {'code': 'db_unavailable', 'message': 'Database is down'}}, status: 503);
    await pumpPage(t, r);
    expect(find.text('Database is down'), findsWidgets);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('390 px wide: no overflow, no overlay', (t) async {
    final r = TasksRig([
      [
        task('a', 'A fairly long task title that has to wrap on a narrow phone screen', date: '2026-03-12', time: '09:30', provider: 'google', eventId: 'evt-1', checklist: const [ChecklistItem(id: 'x', text: 'One')]),
        task('b', 'Someday'),
      ],
    ]);
    await pumpPage(t, r, phone: true);
    expect(t.takeException(), isNull);
    await expectNoOverlays(t);
    expect(r.canned.unmatched, isEmpty);
  });

  testWidgets('the full form creates a task with checklist, date, time, assignee and reminder', (t) async {
    final r = TasksRig([<Object?>[]]);
    r.canned.responses.json('POST', '/tasks', task('n3', 'Everything'), status: 201);
    await pumpPage(t, r);
    final title = find.descendant(of: byId('sdk.tasks.form-title'), matching: find.byType(TextField));
    await t.ensureVisible(title);
    await t.enterText(title, 'Everything');
    final add = find.descendant(of: byId('sdk.tasks.form-checklist-add'), matching: find.byType(TextField));
    for (final line in ['First line', 'Second line']) {
      await t.ensureVisible(add);
      await t.enterText(add, line);
      await t.testTextInput.receiveAction(TextInputAction.done);
      await t.pump();
    }
    await t.ensureVisible(byId('sdk.tasks.form-due-date'));
    await t.tap(byId('sdk.tasks.form-due-date'));
    await t.pump();
    await t.tap(byId('sdk.tasks.form-due-date-day-2026-03-14'));
    await t.pump();
    await t.ensureVisible(find.text('Add a time'));
    await t.tap(find.text('Add a time'));
    await t.pump();
    await t.ensureVisible(find.text('Unassigned'));
    await t.tap(find.text('Unassigned'));
    await t.pump();
    await t.tap(find.text('Viewer User'));
    await t.pump();
    await t.ensureVisible(find.text('1 minute before'));
    await t.tap(find.text('1 minute before'));
    await t.pump();
    await t.ensureVisible(find.text('Save task'));
    await t.tap(find.text('Save task'));
    await settle(t);
    final body = r.only('POST', '/tasks').json as Map;
    expect(body['title'], 'Everything');
    expect(body['due_date'], '2026-03-14');
    expect(body['due_time'], '09:00');
    expect(body['assigned_user_id'], 'demo-user-2');
    expect(body['remind_minutes_before'], 1);
    expect((body['checklist'] as List).map((c) => (c as Map)['text']), ['First line', 'Second line']);
  });

  testWidgets('reopen posts to the reopen route for a done task', (t) async {
    final r = TasksRig([
      [task('c', 'Filed', date: '2026-03-12', status: TaskStatus.done)],
    ]);
    r.canned.responses.json('POST', '/tasks/c/reopen', task('c', 'Filed', date: '2026-03-12'));
    await pumpPage(t, r);
    await t.tap(find.byIcon(Icons.check_circle));
    await settle(t);
    expect(r.canned.requestsTo('POST', '/tasks/c/reopen'), hasLength(1));
    expect(r.canned.requestsTo('POST', '/tasks/c/complete'), isEmpty);
  });

  testWidgets('the mirror result shows for the second provider too', (t) async {
    final r = TasksRig([
      [task('m', 'Mirrored', date: '2026-03-12', provider: 'microsoft', eventId: 'evt-9')],
    ]);
    await pumpPage(t, r);
    expect(textOf(t, 'sdk.tasks.external-m'), 'Calendar: microsoft evt-9');
  });

  testWidgets('turning the mirror off puts mirror_enabled false and the external id goes away', (t) async {
    final r = TasksRig([
      [task('m', 'Mirrored', date: '2026-03-12', provider: 'google', eventId: 'evt-1')],
      [task('m', 'Mirrored', date: '2026-03-12', mirror: false)],
    ]);
    r.canned.responses.json('PUT', '/tasks/m', task('m', 'Mirrored', date: '2026-03-12', mirror: false));
    await pumpPage(t, r);
    expect(byId('sdk.tasks.external-m'), findsWidgets);
    await t.tap(byId('sdk.tasks.mirror-m'));
    await settle(t);
    expect(r.only('PUT', '/tasks/m').json, {'mirror_enabled': false});
    expect(byId('sdk.tasks.external-m'), findsNothing);
    expect(find.text('Calendar: off'), findsOneWidget);
  });

  testWidgets('a sign-in failure is shown, not thrown', (t) async {
    final r = TasksRig([<Object?>[]]);
    setWideScreen(t, size: const Size(900, 3600));
    await pumpApp(
      t,
      TasksPage(
        api: r.api,
        jobs: r.jobs,
        ensureSignedIn: () async => throw const AuthFailure(AuthFailureReason.network, message: 'The server is not reachable'),
        clock: () => DateTime(2026, 3, 12, 8),
      ),
    );
    await settle(t);
    expect(find.text('The server is not reachable'), findsWidgets);
    expect(t.takeException(), isNull);
    expect(r.canned.requests, isEmpty);
  });
}
