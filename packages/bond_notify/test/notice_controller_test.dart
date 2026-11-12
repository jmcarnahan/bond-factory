import 'dart:async';
import 'dart:convert';

import 'package:bond_api/bond_api.dart';
import 'package:bond_notify/bond_notify.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

final now = DateTime.utc(2026, 11, 12, 12);

/// A notice created [ageMin] minutes before [now] (old by default); null means no createdAt.
Notice n(String id, {bool read = false, int? ageMin = 60}) => Notice(
      id: id,
      title: id,
      createdAt: ageMin == null ? null : now.subtract(Duration(minutes: ageMin)),
      readAt: read ? DateTime.utc(2026, 11, 12) : null,
    );

/// A hand-driven feed: tests push snapshots and choose whether calls fail.
class FakeFeed implements NoticeFeed {
  final _c = StreamController<List<Notice>>.broadcast();
  bool fail = false;
  bool refreshFails = false;
  int? server;
  Completer<void>? gate;
  final calls = <String>[];

  void push(List<Notice> l) => _c.add(l);

  @override
  Stream<List<Notice>> watch() => _c.stream;
  @override
  Future<void> refresh() async {
    calls.add('refresh');
    if (refreshFails) throw StateError('refresh failed');
  }

  @override
  int? get serverUnreadCount => server;

  @override
  Future<void> markAllRead() async {
    calls.add('read-all');
    await gate?.future;
    if (fail) throw StateError('nope');
  }
  @override
  Future<void> markRead(String id) async {
    calls.add('read $id');
    await gate?.future;
    if (fail) throw StateError('nope');
  }

  @override
  Future<void> dismiss(String id) async {
    calls.add('dismiss $id');
    await gate?.future;
    if (fail) throw StateError('nope');
  }

  @override
  void dispose() => _c.close();
}

Future<void> pause() => Future<void>.delayed(const Duration(milliseconds: 5));

void main() {
  late FakeFeed feed;
  late NoticeController c;
  late List<NoticeState> states;
  late List<Notice> alerts;

  setUp(() async {
    feed = FakeFeed();
    c = NoticeController(feed, clock: () => now);
    states = [];
    alerts = [];
    c.states.listen(states.add);
    c.newUnread.listen(alerts.add);
    await c.start();
    await pause();
  });
  tearDown(() {
    c.dispose();
    feed.dispose();
  });

  test('start refreshes, shows loading, then items and the unread count', () async {
    expect(feed.calls, ['refresh']);
    expect(states.first.loading, isTrue);
    feed.push([n('a'), n('b', read: true), n('c')]);
    await pause();
    expect(states.last.loading, isFalse);
    expect(states.last.unreadCount, 2);
    expect(states.last.items.length, 3);
  });

  test('states replays the latest value to a late listener', () async {
    feed.push([n('a')]);
    await pause();
    final s = await c.states.first.timeout(const Duration(seconds: 1));
    expect(s.items.single.id, 'a');
  });

  test('old unread notices in the first snapshot do not alert; a fresh one does', () async {
    feed.push([n('old1'), n('old2'), n('just', ageMin: 2)]);
    await pause();
    expect(alerts.map((a) => a.id), ['just']);
  });

  test('an empty first snapshot followed by old notices does not alert', () async {
    feed.push([]);
    await pause();
    feed.push([n('old1', ageMin: 11), n('old2', ageMin: 600)]);
    await pause();
    expect(alerts, isEmpty);
  });

  test('freshness edge: exactly ten minutes old alerts, eleven does not', () async {
    feed.push([n('edge', ageMin: 10), n('past', ageMin: 11)]);
    await pause();
    expect(alerts.map((a) => a.id), ['edge']);
  });

  test('read, dismissed and createdAt-less notices never alert', () async {
    feed.push([n('r', read: true, ageMin: 1), n('nodate', ageMin: null)]);
    await pause();
    expect(alerts, isEmpty);
  });

  test('each id alerts exactly once, even when it leaves and returns', () async {
    feed.push([]);
    await pause();
    feed.push([n('new', ageMin: 1)]);
    await pause();
    feed.push([n('new', ageMin: 1), n('old1')]);
    await pause();
    feed.push([n('other', read: true), n('old1')]);
    await pause();
    feed.push([n('new', ageMin: 1)]);
    await pause();
    expect(alerts.map((a) => a.id), ['new']);
  });

  test('markRead is optimistic and is kept on success', () async {
    feed.push([n('a'), n('b')]);
    await pause();
    feed.gate = Completer<void>();
    final f = c.markRead('a');
    await pause();
    expect(states.last.unreadCount, 1, reason: 'changed before the call finished');
    expect(states.last.items.first.unread, isFalse);
    feed.gate!.complete();
    await f;
    await pause();
    expect(states.last.unreadCount, 1);
    expect(states.last.error, isNull);
  });

  test('markRead failure restores the notice and sets the error', () async {
    feed.push([n('a'), n('b')]);
    await pause();
    feed.fail = true;
    await c.markRead('a');
    await pause();
    expect(states.last.unreadCount, 2);
    expect(states.last.items.first.unread, isTrue);
    expect(states.last.error, isA<StateError>());
  });

  test('dismiss is optimistic; failure puts the notice back where it was', () async {
    feed.push([n('a'), n('b'), n('c')]);
    await pause();
    feed.gate = Completer<void>();
    feed.fail = true;
    final f = c.dismiss('b');
    await pause();
    expect(states.last.items.map((x) => x.id), ['a', 'c']);
    feed.gate!.complete();
    await f;
    await pause();
    expect(states.last.items.map((x) => x.id), ['a', 'b', 'c']);
    expect(states.last.unreadCount, 3);
    expect(states.last.error, isNotNull);
  });

  test('dismissing an already-read notice leaves the unread count alone, never negative', () async {
    feed.push([n('a'), n('r', read: true)]);
    await pause();
    expect(states.last.unreadCount, 1);
    await c.dismiss('r');
    await pause();
    expect(states.last.unreadCount, 1);
    expect(states.last.items.map((x) => x.id), ['a']);
    await c.dismiss('a');
    await pause();
    expect(states.last.unreadCount, 0);
    // A failed dismiss of a read notice restores it without touching the count.
    feed.push([n('a2'), n('r2', read: true)]);
    await pause();
    feed.fail = true;
    await c.dismiss('r2');
    await pause();
    expect(states.last.unreadCount, 1);
    expect(states.last.items.map((x) => x.id), ['a2', 'r2']);
  });

  test('start is idempotent', () async {
    await c.start();
    await c.start();
    expect(feed.calls.where((e) => e == 'refresh'), hasLength(1));
  });

  test('refresh delegates to the feed and never throws; the error lands in state', () async {
    await c.refresh();
    expect(feed.calls.where((e) => e == 'refresh'), hasLength(2));
    feed.refreshFails = true;
    await c.refresh();
    await pause();
    expect(states.last.error, isA<StateError>());
  });

  test('markAllRead is optimistic and keeps the result on success', () async {
    feed.push([n('a'), n('b'), n('c', read: true)]);
    await pause();
    feed.gate = Completer<void>();
    final f = c.markAllRead();
    await pause();
    expect(states.last.unreadCount, 0);
    expect(states.last.items.every((x) => !x.unread), isTrue);
    feed.gate!.complete();
    await f;
    await pause();
    expect(feed.calls, contains('read-all'));
    expect(states.last.unreadCount, 0);
    expect(states.last.error, isNull);
  });

  test('markAllRead failure puts the unread notices back and sets the error', () async {
    feed.push([n('a'), n('b'), n('c', read: true)]);
    await pause();
    feed.fail = true;
    await c.markAllRead();
    await pause();
    expect(states.last.unreadCount, 2);
    expect(states.last.items.where((x) => x.unread).map((x) => x.id), ['a', 'b']);
    expect(states.last.error, isA<StateError>());
  });

  test('with a server count of 60 the badge shows 60 and moves by one per read or dismiss', () async {
    feed.server = 60;
    feed.push([for (var i = 0; i < 50; i++) n('u$i')]);
    await pause();
    expect(states.last.unreadCount, 60, reason: 'not the 50 held');
    await c.markRead('u0');
    await pause();
    expect(states.last.unreadCount, 59);
    await c.dismiss('u1');
    await pause();
    expect(states.last.unreadCount, 58);
    await c.markRead('u0'); // already read: no change
    await pause();
    expect(states.last.unreadCount, 58);
  });

  test('with a server count, a failed read puts the count back; read-all gives 0', () async {
    feed.server = 60;
    feed.push([for (var i = 0; i < 3; i++) n('u$i')]);
    await pause();
    feed.fail = true;
    await c.markRead('u0');
    await pause();
    expect(states.last.unreadCount, 60);
    feed.fail = false;
    await c.markAllRead();
    await pause();
    expect(states.last.unreadCount, 0);
  });

  test('a feed error becomes state.error and a later snapshot clears it', () async {
    feed._c.addError(StateError('down'));
    await pause();
    expect(states.last.error, isA<StateError>());
    expect(states.last.loading, isFalse);
    feed.push([n('a')]);
    await pause();
    expect(states.last.error, isNull);
  });

  test('paging cursor: NoticesApi passes before through', () async {
    late http.Request seen;
    final api = NoticesApi(ApiClient(
      baseUrl: Uri.parse('https://api.test'),
      http: MockClient((r) async {
        seen = r;
        return http.Response(jsonEncode({'items': [], 'unread_count': 0}), 200,
            headers: {'content-type': 'application/json'});
      }),
    ));
    await api.list(limit: 50, before: '2026-11-12T10:00:00Z|abc');
    expect(seen.url.queryParameters['before'], '2026-11-12T10:00:00Z|abc');
  });
}
