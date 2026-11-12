import 'dart:async';

import 'package:bond_push/bond_push.dart';
import 'package:bond_push/testing.dart';
import 'package:flutter_test/flutter_test.dart';

class FakePlugin implements PushPlugin {
  final tokens = <String?>[];
  int tokenReads = 0;
  bool permission = true;
  int permissionCalls = 0;
  final _newToken = <void Function(String)>[];
  final _tap = <void Function(Map<String?, Object?>)>[];
  Map<String?, Object?>? launch;

  void refresh(String t) {
    for (final h in [..._newToken]) {
      h(t);
    }
  }

  void tap(Map<String?, Object?> p) {
    for (final h in [..._tap]) {
      h(p);
    }
  }

  int get newTokenListeners => _newToken.length;

  @override
  Future<String?> getToken() async {
    final i = tokenReads++;
    return i < tokens.length ? tokens[i] : (tokens.isEmpty ? null : tokens.last);
  }

  @override
  void Function() addOnNewToken(void Function(String) h) {
    _newToken.add(h);
    return () => _newToken.remove(h);
  }

  @override
  Future<bool> requestPermission() async {
    permissionCalls++;
    return permission;
  }

  @override
  void Function() addOnNotificationTap(void Function(Map<String?, Object?>) h) {
    _tap.add(h);
    return () => _tap.remove(h);
  }

  @override
  Future<Map<String?, Object?>?> launchTap() async => launch;
}

class FakeDevices implements PushDevices {
  final registered = <PushToken>[];
  final unregistered = <String>[];
  Object? failRegister;
  Object? failUnregister;
  String? lastTopic;
  int failTimes = 0; // the next N register calls throw
  Completer<void>? registerGate; // register waits for this
  final log = <String>[];

  @override
  Future<void> register(PushToken t, {required String deviceId, String? topic}) async {
    log.add('register-call');
    if (registerGate != null) await registerGate!.future;
    if (failRegister != null) throw failRegister!;
    if (failTimes > 0) {
      failTimes--;
      throw StateError('network down');
    }
    registered.add(t);
    lastTopic = topic;
    log.add('registered');
  }

  @override
  Future<void> unregister(String deviceId) async {
    if (failUnregister != null) throw failUnregister!;
    unregistered.add(deviceId);
    log.add('unregistered');
  }
}

Future<void> pause() => Future<void>.delayed(const Duration(milliseconds: 5));

void main() {
  group('PluginPushTokenSource', () {
    test('maps the hex token with platform ios and the given environment', () async {
      final p = FakePlugin()..tokens.add('ab12');
      final s = PluginPushTokenSource(environment: 'sandbox', plugin: p);
      expect(await s.token(), const PushToken(value: 'ab12', platform: 'ios', environment: 'sandbox'));
    });

    test('null and empty tokens are null', () async {
      final p = FakePlugin()..tokens.addAll([null, '']);
      final s = PluginPushTokenSource(plugin: p);
      expect(await s.token(), isNull);
      expect(await s.token(), isNull);
    });

    test('onRefresh forwards new tokens and unsubscribes on cancel', () async {
      final p = FakePlugin();
      final s = PluginPushTokenSource(environment: 'sandbox', plugin: p);
      final got = <PushToken>[];
      final sub = s.onRefresh.listen(got.add);
      expect(p.newTokenListeners, 1);
      p.refresh('t2');
      await pause();
      expect(got.single, const PushToken(value: 't2', environment: 'sandbox'));
      await sub.cancel();
      expect(p.newTokenListeners, 0);
    });

    test('requestPermission passes the answer through', () async {
      final p = FakePlugin()..permission = false;
      final s = PluginPushTokenSource(plugin: p);
      expect(await s.requestPermission(), isFalse);
      p.permission = true;
      expect(await s.requestPermission(), isTrue);
      expect(p.permissionCalls, 2);
    });
  });

  group('PluginPushTaps', () {
    test('a tap payload maps to route and notice id, action always null', () async {
      final p = FakePlugin();
      final taps = PluginPushTaps(plugin: p);
      final got = <PushTap>[];
      final sub = taps.taps.listen(got.add);
      p.tap({'notice_id': 'n1', 'task_id': 't1', 'route': '/tasks/t1', 'aps': {'alert': 'x'}});
      p.tap({'data': {'notice_id': 'n2', 'route': '/tasks/t2'}});
      p.tap({'something': 'else'}); // not ours
      await pause();
      expect(got, [
        const PushTap(route: '/tasks/t1', noticeId: 'n1'),
        const PushTap(route: '/tasks/t2', noticeId: 'n2'),
      ]);
      expect(got.every((t) => t.action == null), isTrue);
      await sub.cancel();
      expect(p._tap, isEmpty);
    });

    test('initialTap maps the launching tap, or is null', () async {
      final p = FakePlugin();
      final taps = PluginPushTaps(plugin: p);
      expect(await taps.initialTap(), isNull);
      p.launch = {'notice_id': 'n9', 'route': '/tasks/t9'};
      expect(await taps.initialTap(), const PushTap(route: '/tasks/t9', noticeId: 'n9'));
    });
  });

  group('PushRegistrar', () {
    test('registers the token and never asks for permission', () async {
      final p = FakePlugin()..tokens.add('tok');
      final d = FakeDevices();
      final r = PushRegistrar(PluginPushTokenSource(plugin: p), d, deviceId: 'dev', topic: 'com.example', delay: (_) async {});
      await r.start();
      expect(d.registered.single.value, 'tok');
      expect(d.lastTopic, 'com.example');
      expect(p.permissionCalls, 0);
      r.dispose();
    });

    test('a late token is retried every 2 seconds until it arrives', () async {
      final p = FakePlugin()..tokens.addAll([null, null, null, 'late']);
      final d = FakeDevices();
      final waits = <Duration>[];
      final r = PushRegistrar(PluginPushTokenSource(plugin: p), d, deviceId: 'dev', delay: (w) async => waits.add(w));
      await r.start();
      expect(d.registered.single.value, 'late');
      expect(waits, List.filled(3, const Duration(seconds: 2)));
      r.dispose();
    });

    test('gives up after 5 retries without throwing', () async {
      final p = FakePlugin(); // always null
      final d = FakeDevices();
      var waits = 0;
      final r = PushRegistrar(PluginPushTokenSource(plugin: p), d, deviceId: 'dev', delay: (_) async => waits++);
      await r.start();
      expect(p.tokenReads, 6);
      expect(waits, 5);
      expect(d.registered, isEmpty);
      r.dispose();
    });

    test('every refresh registers again', () async {
      final p = FakePlugin()..tokens.add('one');
      final d = FakeDevices();
      final r = PushRegistrar(PluginPushTokenSource(plugin: p), d, deviceId: 'dev', delay: (_) async {});
      await r.start();
      p.refresh('two');
      await pause();
      expect(d.registered.map((t) => t.value), ['one', 'two']);
      r.dispose();
    });

    test('a failing register goes to errors, not out of start', () async {
      final p = FakePlugin()..tokens.add('tok');
      final d = FakeDevices()..failRegister = StateError('503');
      final r = PushRegistrar(PluginPushTokenSource(plugin: p), d, deviceId: 'dev', delay: (_) async {});
      final errs = <Object>[];
      r.errors.listen(errs.add);
      await r.start();
      await pause();
      expect(errs, hasLength(6), reason: 'the first try and 5 retries, each reported');
      expect(errs.first, isA<StateError>());
      r.dispose();
    });

    test('unregister calls the service and stops listening for refreshes', () async {
      final p = FakePlugin()..tokens.add('tok');
      final d = FakeDevices();
      final r = PushRegistrar(PluginPushTokenSource(plugin: p), d, deviceId: 'dev', delay: (_) async {});
      await r.start();
      await r.unregister();
      expect(d.unregistered, ['dev']);
      p.refresh('after');
      await pause();
      expect(d.registered.map((t) => t.value), ['tok']);
      expect(p.newTokenListeners, 0);
      r.dispose();
    });

    test('a second start while started is a no-op (one retry loop, one listener)', () async {
      final p = FakePlugin()..tokens.addAll([null, null, 'tok']);
      final d = FakeDevices();
      final gate = Completer<void>();
      final r = PushRegistrar(PluginPushTokenSource(plugin: p), d, deviceId: 'dev', delay: (_) => gate.future);
      final first = r.start();
      await pause();
      final second = r.start();
      gate.complete();
      await Future.wait([first, second]);
      expect(p.tokenReads, 3, reason: 'one loop reads 3 times; two loops would read more');
      expect(d.registered, hasLength(1));
      expect(p.newTokenListeners, 1);
      r.dispose();
    });

    test('after unregister the same instance can start again', () async {
      final p = FakePlugin()..tokens.add('tok');
      final d = FakeDevices();
      final r = PushRegistrar(PluginPushTokenSource(plugin: p), d, deviceId: 'dev', delay: (_) async {});
      await r.start();
      await r.unregister();
      await r.start();
      expect(d.registered.map((t) => t.value), ['tok', 'tok']);
      p.refresh('fresh');
      await pause();
      expect(d.registered.map((t) => t.value), ['tok', 'tok', 'fresh']);
      r.dispose();
    });

    test('a loop still waiting when unregister is called does not register afterwards', () async {
      final p = FakePlugin()..tokens.addAll([null, 'tok']);
      final d = FakeDevices();
      final gate = Completer<void>();
      final r = PushRegistrar(PluginPushTokenSource(plugin: p), d, deviceId: 'dev', delay: (_) => gate.future);
      final f = r.start();
      await pause();
      await r.unregister();
      gate.complete();
      await f;
      expect(d.registered, isEmpty);
    });

    test('a register that throws is retried on the same schedule, each error reported', () async {
      final p = FakePlugin()..tokens.add('tok');
      final d = FakeDevices()..failTimes = 2;
      final waits = <Duration>[];
      final r = PushRegistrar(PluginPushTokenSource(plugin: p), d, deviceId: 'dev', delay: (w) async => waits.add(w));
      final errs = <Object>[];
      r.errors.listen(errs.add);
      await r.start();
      await pause();
      expect(d.registered.single.value, 'tok');
      expect(waits, List.filled(2, const Duration(seconds: 2)));
      expect(errs, hasLength(2));
      r.dispose();
    });

    test('a register that never succeeds stops after the retries', () async {
      final p = FakePlugin()..tokens.add('tok');
      final d = FakeDevices()..failTimes = 100;
      var waits = 0;
      final r = PushRegistrar(PluginPushTokenSource(plugin: p), d, deviceId: 'dev', delay: (_) async => waits++);
      await r.start();
      expect(waits, 5);
      expect(d.log.where((e) => e == 'register-call'), hasLength(6));
      r.dispose();
    });

    test('unregister waits for a register in flight, so the device ends unregistered', () async {
      final p = FakePlugin()..tokens.add('tok');
      final d = FakeDevices()..registerGate = Completer<void>();
      final r = PushRegistrar(PluginPushTokenSource(plugin: p), d, deviceId: 'dev', delay: (_) async {});
      final started = r.start();
      await pause();
      expect(d.log, ['register-call']);
      final out = r.unregister();
      await pause();
      expect(d.unregistered, isEmpty, reason: 'must wait for the register on the wire');
      d.registerGate!.complete();
      await Future.wait([started, out]);
      expect(d.log, ['register-call', 'registered', 'unregistered']);
      r.dispose();
    });

    test('a failing unregister is reported, not thrown', () async {
      final p = FakePlugin()..tokens.add('tok');
      final d = FakeDevices()..failUnregister = StateError('offline');
      final r = PushRegistrar(PluginPushTokenSource(plugin: p), d, deviceId: 'dev', delay: (_) async {});
      final errs = <Object>[];
      r.errors.listen(errs.add);
      await r.start();
      await r.unregister();
      await pause();
      expect(errs, hasLength(1));
      r.dispose();
    });
  });
}
