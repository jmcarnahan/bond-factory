import 'dart:async';

import 'package:bond_api/bond_api.dart';
import 'package:bond_tasks_notifications/testing.dart';
import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/example_api.dart';
import 'package:sdk_demo/src/todo/todo_alerts.dart';
import 'package:sdk_demo/src/todo/todo_services.dart';

import 'todo_rig.dart';

Map<String, Object?> answer(String token, String user) => {
      'token': token,
      'user': {'id': user, 'email': 'demo@example.com', 'name': 'Demo User', 'capabilities': <String>[]},
    };

void main() {
  final originalFactory = TodoAlerts.pluginFactory;
  tearDown(() async {
    DemoSession.signInHooks.clear();
    DemoSession.signOutHooks.clear();
    await TodoAlerts.stop();
    TodoAlerts.pluginFactory = originalFactory;
  });

  group('the alerts follow the session', () {
    late List<FakeAlertPlugin> plugins;
    late CannedHttpClient http;

    void rig(CannedResponses r) {
      r
        ..json('GET', '/tasks', {'items': <Object?>[], 'total': 0})
        ..json('GET', '/tasks/settings', {
          'time_zone': 'UTC',
          'start_of_day': '08:00',
          'end_of_day': '17:00',
          'lead_minutes': 60,
          'warnings': <Object?>[],
        })
        ..json('GET', '/notices', {'items': <Object?>[], 'unread_count': 0});
      http = CannedHttpClient(r);
      DemoSession.reset(client: http, base: Uri.parse('http://test.invalid'));
      TodoServices.resetShared();
      addTearDown(() {
        DemoSession.reset();
        TodoServices.resetShared();
      });
      plugins = [];
      TodoAlerts.pluginFactory = () {
        final p = FakeAlertPlugin();
        plugins.add(p);
        return p;
      };
      TodoAlerts.install();
    }

    test('a session the server ended stops the alerts', () async {
      rig(CannedResponses()
        ..json('POST', '/auth/demo', answer('t-one', 'demo-user-1'))
        ..json('GET', '/auth/me', {'detail': {'code': 'invalid_token', 'message': 'bad'}}, status: 401)
        ..json('POST', '/auth/demo', {'detail': {'code': 'deactivated', 'message': 'off'}}, status: 403));
      await DemoSession.ensureSignedIn();
      await TodoAlerts.settled;
      expect(TodoAlerts.running, isTrue);
      expect(TodoAlerts.runningFor, 'demo-user-1');

      DemoSession.tokens.token = 'broken.token.value';
      await expectLater(DemoSession.api.getJson('/auth/me'), throwsA(isA<Unauthorized>()));
      await TodoAlerts.settled;
      expect(DemoSession.session, isNull);
      expect(TodoAlerts.running, isFalse);
      expect(plugins.single.scheduled, isEmpty);
    });

    test('switching to another person restarts the alerts for that person', () async {
      rig(CannedResponses()
        ..json('POST', '/auth/demo', answer('t-one', 'demo-user-1'))
        ..json('POST', '/auth/demo', answer('t-two', 'demo-user-2')));
      await DemoSession.signInDemo('demo-user-1');
      await TodoAlerts.settled;
      expect(TodoAlerts.runningFor, 'demo-user-1');

      await DemoSession.signInDemo('demo-user-2');
      await TodoAlerts.settled;
      expect(TodoAlerts.runningFor, 'demo-user-2');
      expect(plugins, hasLength(2), reason: 'a new coordinator, with its own plugin');
      expect(plugins[1].initialised, isTrue);
    });

    test('a refresh for the same person does not restart anything', () async {
      rig(CannedResponses()
        ..json('POST', '/auth/demo', answer('t-one', 'demo-user-1'))
        ..json('POST', '/auth/refresh', answer('t-r', 'demo-user-1')));
      await DemoSession.signInDemo('demo-user-1');
      await TodoAlerts.settled;
      await DemoSession.refresh();
      await TodoAlerts.settled;
      expect(plugins, hasLength(1));
    });

    test('sign-out stops the alerts', () async {
      rig(CannedResponses()
        ..json('POST', '/auth/demo', answer('t-one', 'demo-user-1'))
        ..json('POST', '/auth/logout', <String, Object?>{}));
      await DemoSession.signInDemo('demo-user-1');
      await TodoAlerts.settled;
      await DemoSession.signOut();
      await TodoAlerts.settled;
      expect(TodoAlerts.running, isFalse);
    });
  });

  group('start and stop in a race', () {
    test('a stop during a start leaves nothing running', () async {
      final r = TodoRig();
      r.baseline();
      final gate = r.holds['GET /tasks/settings'] = Completer<void>();
      final plugin = FakeAlertPlugin();

      final started = TodoAlerts.start(r.services, plugin: plugin);
      final stopped = TodoAlerts.stop();
      await Future<void>.delayed(const Duration(milliseconds: 20));
      gate.complete();
      await Future.wait([started, stopped]);

      expect(TodoAlerts.running, isFalse);
      expect(plugin.scheduled, isEmpty);
    });

    test('a stop then a start for another person ends with that person\'s coordinator', () async {
      final one = TodoRig(user: 'demo-user-1')..baseline();
      final two = TodoRig(user: 'demo-user-2')..baseline();
      final gate = one.holds['GET /tasks/settings'] = Completer<void>();
      final p1 = FakeAlertPlugin();
      final p2 = FakeAlertPlugin();

      final a = TodoAlerts.start(one.services, plugin: p1);
      final b = TodoAlerts.stop();
      final c = TodoAlerts.start(two.services, plugin: p2);
      await Future<void>.delayed(const Duration(milliseconds: 20));
      gate.complete();
      await Future.wait([a, b, c]);

      expect(TodoAlerts.runningFor, 'demo-user-2');
      expect(p2.initialised, isTrue);
      expect(p1.scheduled, isEmpty);
    });
  });
}
