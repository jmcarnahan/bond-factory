import 'dart:convert';
import 'dart:io';

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_notify_powersync/bond_notify_powersync.dart';
import 'package:bond_push/bond_push.dart';
import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_sync_powersync/testing.dart';
import 'package:flutter_test/flutter_test.dart';

final clockNow = DateTime.utc(2026, 11, 12, 15, 0, 7);
final dev1Id = SyncPushDevices(FakeSyncDb(), userId: 'user-1').rowId('dev1');
final dev2Id = SyncPushDevices(FakeSyncDb(), userId: 'user-1').rowId('dev2');
const stamp = '2026-11-12T15:00:07.000Z';

List<SyncRow> fixtureRows() {
  final page = jsonDecode(File('../../fixtures/notify/notices_page.json').readAsStringSync()) as Map;
  return [
    for (final n in page['items'] as List)
      {...(n as Map).cast<String, Object?>(), 'data': jsonEncode(n['data'])},
  ];
}

Set<String> cols(String table) {
  final t = [...noticesTables(), ...pushDevicesTables()].firstWhere((t) => t.name == table);
  return {'id', for (final c in t.columns) c.name};
}

FakeSyncDb noticeDb(List<SyncRow> rows) =>
    FakeSyncDb.tables({'notices': rows}, applySql: true, columns: {'notices': cols('notices')});

List<Stmt> writes(FakeSyncDb db) => [
      for (final s in db.statements)
        if (RegExp(r'^(INSERT|UPDATE|DELETE)').hasMatch(s.sql)) s,
    ];

void main() {
  test('tables declare the columns and an index', () {
    final n = noticesTables().single;
    expect(n.columns.map((c) => c.name), ['user_id', 'kind', 'title', 'body', 'data', 'created_at', 'read_at', 'dismissed_at']);
    expect(n.indexes.single.columns.map((c) => c.column), ['user_id', 'created_at']);
    final d = pushDevicesTables().single;
    expect(d.name, 'push_devices');
    expect(d.columns.map((c) => c.name),
        ['user_id', 'device_id', 'token', 'platform', 'environment', 'topic', 'last_seen_at', 'disabled_at', 'created_at']);
  });

  group('noticeFromRow', () {
    test('every fixture notice decodes like the wire notice', () {
      final page = jsonDecode(File('../../fixtures/notify/notices_page.json').readAsStringSync()) as Map;
      final rows = fixtureRows();
      for (var i = 0; i < rows.length; i++) {
        final want = Notice.fromJson((page['items'] as List)[i] as Map<String, Object?>);
        expect(noticeFromRow(rows[i]).toJson(), want.toJson());
      }
    });

    test('a datetime without a Z is UTC; a malformed data cell keeps the notice', () {
      final n = noticeFromRow({...fixtureRows().first, 'created_at': '2026-11-12T14:30:05', 'data': '{oops'});
      expect(n.createdAt, DateTime.utc(2026, 11, 12, 14, 30, 5));
      expect(n.taskId, isNull);
      expect(n.title, startsWith('Due now'));
      expect(noticeFromRow({...fixtureRows().first, 'data': '[1]'}).taskId, isNull);
    });
  });

  group('WatchNoticeFeed', () {
    WatchNoticeFeed feed(FakeSyncDb db) => WatchNoticeFeed(db, userId: 'user-1', now: () => clockNow);

    test('newest first, dismissed rows hidden, other users hidden', () async {
      final rows = fixtureRows();
      final dismissed = {...rows[0], 'id': 'gone', 'dismissed_at': '2026-11-12T16:00:00Z'};
      final other = {...rows[0], 'id': 'other', 'user_id': 'user-2'};
      final sameTime = {...rows[2], 'id': 'zz', 'created_at': rows[2]['created_at']};
      final db = noticeDb([rows[2], rows[0], dismissed, other, rows[1], sameTime]);
      final list = await feed(db).watch().first;
      expect(list.map((n) => n.id), [
        '4bef1b8888fef279d89a41fdbd63b326',
        '55daa401f514c48bcfe12819d89444b8',
        'zz',
        '3a176fec02c0ee0ccb3f18d6584ca7cb',
      ]);
      final read = db.statements.firstWhere((s) => s.sql.startsWith('SELECT'));
      expect(read.sql, 'SELECT * FROM notices WHERE user_id = ? AND dismissed_at IS NULL ORDER BY created_at DESC, id DESC');
      expect(read.params, ['user-1']);
    });

    test('markRead sets read_at once, locally, and the watch emits the change', () async {
      final db = noticeDb(fixtureRows());
      final f = feed(db);
      final seen = <List<bool>>[];
      final sub = f.watch().listen((l) => seen.add([for (final n in l) n.unread]));
      await pumpEventQueue();
      await f.markRead('4bef1b8888fef279d89a41fdbd63b326');
      await pumpEventQueue();
      await sub.cancel();
      final w = writes(db).single;
      expect(w.sql, 'UPDATE notices SET read_at = ? WHERE id = ? AND user_id = ? AND read_at IS NULL');
      expect(w.params, [stamp, '4bef1b8888fef279d89a41fdbd63b326', 'user-1']);
      expect(w.inTx, isTrue);
      expect(seen, [
        [true, true, false],
        [false, true, false],
      ]);
    });

    test('markRead leaves an earlier read_at alone', () async {
      final db = noticeDb(fixtureRows());
      await feed(db).markRead('3a176fec02c0ee0ccb3f18d6584ca7cb');
      final row = db.tables['notices']!.firstWhere((r) => r['id'] == '3a176fec02c0ee0ccb3f18d6584ca7cb');
      expect(row['read_at'], '2026-11-10T21:05:00Z');
    });

    test('markAllRead is one UPDATE of the user\'s unread, undismissed rows; serverUnreadCount is null', () async {
      final rows = fixtureRows();
      final dismissed = {...rows[0], 'id': 'gone', 'dismissed_at': '2026-11-12T16:00:00Z'};
      final other = {...rows[0], 'id': 'other', 'user_id': 'user-2'};
      final db = noticeDb([...rows, dismissed, other]);
      final f = feed(db);
      expect(f.serverUnreadCount, isNull);
      await f.markAllRead();
      final w = writes(db).single;
      expect(w.sql, 'UPDATE notices SET read_at = ? WHERE user_id = ? AND read_at IS NULL AND dismissed_at IS NULL');
      expect(w.params, [stamp, 'user-1']);
      final byId = {for (final r in db.tables['notices']!) r['id']: r['read_at']};
      expect(byId['4bef1b8888fef279d89a41fdbd63b326'], stamp);
      expect(byId['55daa401f514c48bcfe12819d89444b8'], stamp);
      expect(byId['3a176fec02c0ee0ccb3f18d6584ca7cb'], '2026-11-10T21:05:00Z'); // already read: kept
      expect(byId['gone'], isNull);
      expect(byId['other'], isNull);
    });

    test('dismiss hides the notice', () async {
      final db = noticeDb(fixtureRows());
      final f = feed(db);
      await f.dismiss('55daa401f514c48bcfe12819d89444b8');
      final w = writes(db).single;
      expect(w.sql, 'UPDATE notices SET dismissed_at = ? WHERE id = ? AND user_id = ? AND dismissed_at IS NULL');
      expect(w.params, [stamp, '55daa401f514c48bcfe12819d89444b8', 'user-1']);
      expect((await f.watch().first).map((n) => n.id), isNot(contains('55daa401f514c48bcfe12819d89444b8')));
    });

    test('another user cannot touch the row; refresh is a no-op', () async {
      final db = noticeDb(fixtureRows());
      await WatchNoticeFeed(db, userId: 'user-2', now: () => clockNow).markRead('4bef1b8888fef279d89a41fdbd63b326');
      expect(db.tables['notices']!.first['read_at'], isNull);
      await feed(db).refresh();
      feed(db).dispose();
    });
  });

  group('SyncPushDevices', () {
    test('the row id always matches the sync id rule, for any ids', () {
      final rule = RegExp(r'^[A-Za-z0-9_-]{1,64}$'); // the dispatcher's id rule
      const uuid = '3f2b8c1e-9d4a-4b7e-8a61-5c0d2e7f9a10';
      final ids = {
        SyncPushDevices(FakeSyncDb(), userId: uuid).rowId('D' * 64),
        SyncPushDevices(FakeSyncDb(), userId: 'user-1').rowId('dev:1 with spaces/and\u00e9'),
        SyncPushDevices(FakeSyncDb(), userId: 'a' * 200).rowId('b' * 200),
        SyncPushDevices(FakeSyncDb(), userId: 'user-1').rowId('dev1'),
      };
      for (final id in ids) {
        expect(id, matches(rule), reason: id);
      }
      // pinned to the server's literal for the same inputs, so the two sides cannot drift
      expect(SyncPushDevices(FakeSyncDb(), userId: 'u1').rowId('device-0001'), 'd_dc3d1e5ab21c3dc51c4d543ffbbb9f7c');
      expect(ids, hasLength(4)); // distinct inputs, distinct ids
      expect(SyncPushDevices(FakeSyncDb(), userId: 'u').rowId('d'), SyncPushDevices(FakeSyncDb(), userId: 'u').rowId('d'));
      // the separator keeps ("a|b", "c") and ("a", "b|c") apart only by hashing both parts in order
      expect(SyncPushDevices(FakeSyncDb(), userId: 'ab').rowId('c'), isNot(SyncPushDevices(FakeSyncDb(), userId: 'a').rowId('bc')));
    });

    FakeSyncDb deviceDb() =>
        FakeSyncDb.tables({'push_devices': []}, applySql: true, columns: {'push_devices': cols('push_devices')});
    SyncPushDevices devices(FakeSyncDb db) => SyncPushDevices(db, userId: 'user-1', now: () => clockNow);

    test('register inserts the row with the hashed id', () async {
      final db = deviceDb();
      await devices(db).register(const PushToken(value: 'abc', environment: 'sandbox'), deviceId: 'dev1', topic: 'com.example.app');
      final insert = writes(db).single;
      expect(
        insert.sql,
        'INSERT INTO push_devices (id, user_id, device_id, token, platform, environment, topic, last_seen_at, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
      );
      expect(insert.params, [dev1Id, 'user-1', 'dev1', 'abc', 'ios', 'sandbox', 'com.example.app', stamp, stamp]);
      expect(db.tables['push_devices'], hasLength(1));
    });

    test('registering twice is one row, the second a token refresh', () async {
      final db = deviceDb();
      final d = SyncPushDevices(db, userId: 'user-1', now: () => clockNow);
      await d.register(const PushToken(value: 'abc'), deviceId: 'dev1');
      await SyncPushDevices(db, userId: 'user-1', now: () => clockNow.add(const Duration(hours: 1)))
          .register(const PushToken(value: 'def'), deviceId: 'dev1');
      final rows = db.tables['push_devices']!;
      expect(rows, hasLength(1));
      expect(rows.single['token'], 'def');
      expect(rows.single['created_at'], stamp);
      expect(rows.single['last_seen_at'], stamp); // server-owned: the update leaves it
      final update = writes(db).last;
      expect(update.sql, 'UPDATE push_devices SET token = ?, platform = ?, environment = ?, topic = ? WHERE id = ? AND user_id = ?');
      expect(update.params, ['def', 'ios', 'production', null, dev1Id, 'user-1']);
      expect(update.sql, isNot(contains('last_seen_at')));
      expect(update.sql, isNot(contains('disabled_at')));
    });

    test('two devices are two rows; unregister deletes only that one', () async {
      final db = deviceDb();
      final d = devices(db);
      await d.register(const PushToken(value: 'a'), deviceId: 'dev1');
      await d.register(const PushToken(value: 'b'), deviceId: 'dev2');
      await d.unregister('dev1');
      final del = writes(db).last;
      expect(del.sql, 'DELETE FROM push_devices WHERE id = ? AND user_id = ?');
      expect(del.params, [dev1Id, 'user-1']);
      expect(db.tables['push_devices']!.map((r) => r['id']), [dev2Id]);
      await d.unregister('dev1'); // already gone: no error
    });
  });
}
