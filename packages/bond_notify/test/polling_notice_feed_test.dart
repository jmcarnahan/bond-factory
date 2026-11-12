import 'dart:async';
import 'dart:convert';

import 'package:bond_api/bond_api.dart';
import 'package:bond_notify/bond_notify.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

Map<String, Object?> notice(String id, {bool read = false}) => {
      'id': id,
      'user_id': 'u',
      'kind': 'task_due',
      'title': 'T $id',
      'body': 'b',
      'data': {'task_id': 't', 'actions': ['done']},
      'created_at': '2026-11-12T10:00:00Z',
      'read_at': read ? '2026-11-12T10:05:00Z' : null,
      'dismissed_at': null,
    };

http.Response json(Object? b, [int code = 200]) =>
    http.Response(jsonEncode(b), code, headers: {'content-type': 'application/json'});

/// A scriptable server: [list] decides each GET /notices answer.
class Rig {
  final calls = <http.Request>[];
  Future<http.Response> Function(http.Request r)? list;
  late final NoticesApi api = NoticesApi(ApiClient(
    baseUrl: Uri.parse('https://api.test'),
    http: MockClient((r) async {
      calls.add(r);
      final path = r.url.path;
      if (r.method == 'GET') return list!(r);
      if (path.endsWith('/read')) return json(notice(path.split('/')[2]));
      if (path.endsWith('/dismiss')) return json(notice(path.split('/')[2]));
      if (path.endsWith('/read-all')) return json({'unread_count': 0});
      return json({});
    }),
  ));
  int get gets => calls.where((c) => c.method == 'GET').length;
}

Future<void> pause([int ms = 5]) => Future<void>.delayed(Duration(milliseconds: ms));

void main() {
  test('refresh gets the first page of 50 and emits newest first', () async {
    final rig = Rig()..list = (r) async => json({'items': [notice('b'), notice('a')], 'unread_count': 2});
    final feed = PollingNoticeFeed(rig.api, interval: const Duration(hours: 1));
    final got = <List<Notice>>[];
    final sub = feed.watch().listen(got.add);
    await feed.refresh();
    await pause();
    expect(rig.calls.single.url.queryParameters['limit'], '50');
    expect(got.single.map((n) => n.id), ['b', 'a']);
    await sub.cancel();
    feed.dispose();
  });

  test('a new listener gets the last value replayed', () async {
    final rig = Rig()..list = (r) async => json({'items': [notice('a')]});
    final feed = PollingNoticeFeed(rig.api, interval: const Duration(hours: 1));
    final first = feed.watch().listen((_) {});
    await feed.refresh();
    final late = await feed.watch().first.timeout(const Duration(seconds: 1));
    expect(late.single.id, 'a');
    await first.cancel();
    feed.dispose();
  });

  test('the timer runs only while someone listens', () async {
    final rig = Rig()..list = (r) async => json({'items': []});
    final feed = PollingNoticeFeed(rig.api, interval: const Duration(milliseconds: 20));
    await pause(70);
    expect(rig.gets, 0, reason: 'no listener, no polling');
    final sub = feed.watch().listen((_) {});
    await pause(110);
    final while_ = rig.gets;
    expect(while_, greaterThanOrEqualTo(3));
    await sub.cancel();
    await pause(30);
    final after = rig.gets;
    await pause(100);
    expect(rig.gets, after, reason: 'stopped when the last listener left');
    feed.dispose();
  });

  test('a stale answer is dropped', () async {
    final slow = Completer<http.Response>();
    var n = 0;
    final rig = Rig()
      ..list = (r) {
        n++;
        return n == 1 ? slow.future : Future.value(json({'items': [notice('new')]}));
      };
    final feed = PollingNoticeFeed(rig.api, interval: const Duration(hours: 1));
    final got = <List<Notice>>[];
    final sub = feed.watch().listen(got.add);
    final first = feed.refresh();
    await feed.refresh();
    slow.complete(json({'items': [notice('old')]}));
    await first;
    await pause();
    expect(got.map((l) => l.single.id), ['new']);
    await sub.cancel();
    feed.dispose();
  });

  test('an error reaches the stream, the timer goes on, and the next poll recovers', () async {
    var ok = false;
    final rig = Rig()
      ..list = (r) async => ok ? json({'items': [notice('a')]}) : json({'error': 'x'}, 500);
    final feed = PollingNoticeFeed(rig.api, interval: const Duration(milliseconds: 25));
    final errors = <Object>[];
    final got = <List<Notice>>[];
    final sub = feed.watch().listen(got.add, onError: errors.add);
    await pause(80);
    expect(errors, isNotEmpty);
    expect(got, isEmpty);
    ok = true;
    await pause(80);
    expect(got.last.single.id, 'a');
    await sub.cancel();
    feed.dispose();
  });

  test('markRead stamps readAt from the clock; dismiss removes; both emit in place', () async {
    final rig = Rig()..list = (r) async => json({'items': [notice('a'), notice('b')]});
    final stamp = DateTime.utc(2030, 1, 2, 3);
    final feed = PollingNoticeFeed(rig.api, interval: const Duration(hours: 1), clock: () => stamp);
    final got = <List<Notice>>[];
    final sub = feed.watch().listen(got.add);
    await feed.refresh();
    await feed.markRead('a');
    await pause();
    expect(got.last.first.readAt, stamp);
    expect(got.last.last.unread, isTrue);
    await feed.dismiss('b');
    await pause();
    expect(got.last.map((n) => n.id), ['a']);
    expect(rig.calls.map((c) => '${c.method} ${c.url.path}'), contains('POST /notices/a/read'));
    await sub.cancel();
    feed.dispose();
  });

  test('the local readAt is UTC even when the injected clock returns local time', () async {
    final rig = Rig()..list = (r) async => json({'items': [notice('a')]});
    final local = DateTime(2030, 1, 2, 3, 4); // a local (non-UTC) DateTime
    final feed = PollingNoticeFeed(rig.api, interval: const Duration(hours: 1), clock: () => local);
    final got = <List<Notice>>[];
    final sub = feed.watch().listen(got.add);
    await feed.refresh();
    await feed.markRead('a');
    await pause();
    final at = got.last.single.readAt!;
    expect(at.isUtc, isTrue);
    expect(at, local.toUtc());
    await sub.cancel();
    feed.dispose();
  });

  test('the server unread count is carried (60 unread, 50 held) and moves with read and dismiss', () async {
    final items = [for (var i = 0; i < 50; i++) notice('u$i')];
    final rig = Rig()..list = (r) async => json({'items': items, 'unread_count': 60});
    final feed = PollingNoticeFeed(rig.api, interval: const Duration(hours: 1));
    final sub = feed.watch().listen((_) {});
    expect(feed.serverUnreadCount, isNull, reason: 'unknown before the first page');
    await feed.refresh();
    expect(feed.serverUnreadCount, 60);
    await feed.markRead('u0');
    expect(feed.serverUnreadCount, 59);
    await feed.markRead('u0');
    expect(feed.serverUnreadCount, 59, reason: 'already read');
    await feed.dismiss('u1');
    expect(feed.serverUnreadCount, 58);
    await sub.cancel();
    feed.dispose();
  });

  test('markAllRead calls read-all, marks the held list read, takes the new count', () async {
    final rig = Rig()..list = (r) async => json({'items': [notice('a'), notice('b', read: true)], 'unread_count': 7});
    final stamp = DateTime.utc(2030, 1, 2);
    final feed = PollingNoticeFeed(rig.api, interval: const Duration(hours: 1), clock: () => stamp);
    final got = <List<Notice>>[];
    final sub = feed.watch().listen(got.add);
    await feed.refresh();
    await feed.markAllRead();
    await pause();
    expect(rig.calls.last.url.path, '/notices/read-all');
    expect(got.last.every((n) => !n.unread), isTrue);
    expect(got.last.first.readAt, stamp);
    expect(feed.serverUnreadCount, 0);
    await sub.cancel();
    feed.dispose();
  });

  test('a refresh in flight during markRead cannot undo it', () async {
    final slow = Completer<http.Response>();
    var n = 0;
    final rig = Rig()
      ..list = (r) {
        n++;
        return n == 1 ? Future.value(json({'items': [notice('a')]})) : slow.future;
      };
    final feed = PollingNoticeFeed(rig.api, interval: const Duration(hours: 1));
    final got = <List<Notice>>[];
    final sub = feed.watch().listen(got.add);
    await feed.refresh();
    final inflight = feed.refresh();
    await feed.markRead('a');
    slow.complete(json({'items': [notice('a')]})); // the old unread answer
    await inflight;
    await pause();
    expect(got.last.single.unread, isFalse);
    await sub.cancel();
    feed.dispose();
  });
}
