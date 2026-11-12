import 'dart:convert';
import 'dart:io';

import 'package:bond_api/bond_api.dart';
import 'package:bond_json/bond_json.dart';
import 'package:bond_notify/bond_notify.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

Map<String, Object?> _fixture(String name) =>
    jsonDecode(File('../../fixtures/notify/$name').readAsStringSync()) as Map<String, Object?>;

Object? _canon(Object? v, [String key = '']) {
  if (v is Map) return {for (final e in v.entries) e.key: _canon(e.value, e.key as String)};
  if (v is List) return [for (final e in v) _canon(e, key)];
  if (v is String && key.endsWith('_at')) return jiso(DateTime.parse(v));
  return v;
}

http.Response _json(Object? body) =>
    http.Response(jsonEncode(body), 200, headers: {'content-type': 'application/json'});

void main() {
  test('notice.json round trips', () {
    final src = _fixture('notice.json');
    final n = Notice.fromJson(src);
    expect(n.taskId, 'task-0001');
    expect(n.stage, 'due');
    expect(n.actions, ['done', 'snooze', 'cancel']);
    expect(n.unread, isTrue);
    expect(n.last, isFalse);
    expect(_canon(n.toJson()), _canon(src));
  });

  test('notices_page.json parses and read state follows readAt', () {
    final p = NoticePage.fromJson(_fixture('notices_page.json'));
    expect(p.items, isNotEmpty);
    expect(p.unreadCount, isA<int>());
    final n = p.items.first;
    expect(n.copyWith(readAt: DateTime.utc(2026, 11, 12)).unread, isFalse);
  });

  group('NoticesApi', () {
    late List<http.Request> seen;
    late NoticesApi api;

    void rig(Object? body) {
      seen = [];
      api = NoticesApi(ApiClient(
        baseUrl: Uri.parse('https://api.test/v1'),
        http: MockClient((r) async {
          seen.add(r);
          return _json(body);
        }),
      ));
    }

    test('list sends the query', () async {
      rig(_fixture('notices_page.json'));
      await api.list(unread: true, limit: 20, before: 'abc');
      expect(seen.single.method, 'GET');
      expect(seen.single.url.path, '/v1/notices');
      expect(seen.single.url.queryParameters, {'unread': 'true', 'limit': '20', 'before': 'abc'});
    });

    test('read and dismiss', () async {
      rig(_fixture('notice.json'));
      await api.read('n1');
      expect(seen.last.method, 'POST');
      expect(seen.last.url.path, '/v1/notices/n1/read');
      await api.dismiss('n1');
      expect(seen.last.url.path, '/v1/notices/n1/dismiss');
    });

    test('readAll returns the unread count', () async {
      rig({'unread_count': 0});
      expect(await api.readAll(), 0);
      expect(seen.single.url.path, '/v1/notices/read-all');
    });

    test('act posts the action and reads the notice key', () async {
      rig({'notice': _fixture('notice.json'), 'task': <String, Object?>{}});
      final n = await api.act('n1', 'done');
      expect(seen.single.url.path, '/v1/notices/n1/act');
      expect(jsonDecode(seen.single.body), {'action': 'done'});
      expect(n.notice.taskId, 'task-0001');
      expect(n.task, isEmpty);
    });
  });

  test('labels and the feed clock', () {
    expect(const NoticeLabels().unreadCount(1), '1 unread');
    expect(const NoticeLabels().unreadCount(3), '3 unread');
    final api = NoticesApi(ApiClient(baseUrl: Uri.parse('https://api.test/v1'), http: MockClient((_) async => _json({}))));
    final now = DateTime.utc(2026, 3, 12);
    expect(PollingNoticeFeed(api, clock: () => now).clock(), now);
  });

  test('browserNoticeAlert is a no-op on the VM', () async {
    final a = browserNoticeAlert();
    expect(await a.requestPermission(), isFalse);
    a.show(const Notice(id: 'x'));
  });
}
