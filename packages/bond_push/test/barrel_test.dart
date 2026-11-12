import 'dart:convert';

import 'package:bond_api/bond_api.dart';
import 'package:bond_push/bond_push.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('names exist and the no-op sources are inert', () async {
    const source = NoPushTokenSource();
    expect(await source.token(), isNull);
    expect(await source.requestPermission(), isFalse);
    expect(await source.onRefresh.isEmpty, isTrue);
    const taps = NoPushTaps();
    expect(await taps.initialTap(), isNull);
    expect(await taps.taps.isEmpty, isTrue);
    expect(const PushTap(route: '/r', noticeId: 'n', action: 'done'), const PushTap(route: '/r', noticeId: 'n', action: 'done'));
    expect(PluginPushTokenSource().token, isA<Function>());
    expect(PluginPushTaps().initialTap, isA<Function>());
    final registrar = PushRegistrar(source, _Devices(), deviceId: 'd');
    expect(registrar.start, throwsUnimplementedError);
    registrar.dispose();
  });

  test('PushDevicesApi posts and deletes', () async {
    final seen = <String>[];
    Object? body;
    final client = ApiClient(
      baseUrl: Uri.parse('http://x.test'),
      http: MockClient((r) async {
        seen.add('${r.method} ${r.url.path}');
        if (r.method == 'POST') body = jsonDecode(r.body);
        return http.Response(r.method == 'POST' ? '{"device_id":"d1"}' : '', r.method == 'POST' ? 201 : 204);
      }),
    );
    final api = PushDevicesApi(client);
    await api.register(const PushToken(value: 'abc'), deviceId: 'd1', topic: 't');
    await api.unregister('d1');
    expect(seen, ['POST /push/devices', 'DELETE /push/devices/d1']);
    expect(body, {'token': 'abc', 'platform': 'ios', 'environment': 'production', 'device_id': 'd1', 'topic': 't'});
  });
}

class _Devices implements PushDevices {
  @override
  Future<void> register(PushToken t, {required String deviceId, String? topic}) async {}

  @override
  Future<void> unregister(String deviceId) async {}
}
