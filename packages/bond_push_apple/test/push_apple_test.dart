import 'package:bond_push/bond_push.dart';
import 'package:bond_push_apple/bond_push_apple.dart';
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

Future<void> pause() => Future<void>.delayed(const Duration(milliseconds: 5));

class _Devices implements PushDevices {
  final registered = <PushToken>[];

  @override
  Future<void> register(PushToken t, {required String deviceId, String? topic}) async => registered.add(t);

  @override
  Future<void> unregister(String deviceId) async {}
}

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

  group('PushRegistrar over the plugin source', () {
    test('registers the token and never asks for permission', () async {
      final p = FakePlugin()..tokens.add('tok');
      final d = _Devices();
      final r = PushRegistrar(PluginPushTokenSource(plugin: p), d, deviceId: 'dev', topic: 'com.example', delay: (_) async {});
      await r.start();
      expect(d.registered.single.value, 'tok');
      expect(p.permissionCalls, 0);
      r.dispose();
    });

    test('a refresh from the plugin registers again', () async {
      final p = FakePlugin()..tokens.add('one');
      final d = _Devices();
      final r = PushRegistrar(PluginPushTokenSource(plugin: p), d, deviceId: 'dev', delay: (_) async {});
      await r.start();
      p.refresh('two');
      await pause();
      expect(d.registered.map((t) => t.value), ['one', 'two']);
      r.dispose();
    });
  });
}
