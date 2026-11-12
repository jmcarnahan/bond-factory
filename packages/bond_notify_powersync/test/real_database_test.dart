@Tags(['real_db'])
@TestOn('vm')
library;

import 'dart:convert';
import 'dart:io';

import 'package:bond_notify_powersync/bond_notify_powersync.dart';
import 'package:bond_push/bond_push.dart';
import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:powersync/powersync.dart';

/// The notice feed and device registration against a REAL local PowerSync database (no sync service).
final _schema = Schema([...noticesTables(), ...pushDevicesTables(), ...syncSupportTables()]);
var clock = DateTime.utc(2026, 11, 12, 15);

Future<List<SyncCrudEntry>> drain(SyncDb db) async {
  final out = <SyncCrudEntry>[];
  while (true) {
    final tx = await db.nextCrudTransaction();
    if (tx == null) return out;
    out.addAll(tx.entries);
    await tx.complete();
  }
}

/// Inserts as the sync client would on a download: straight into the raw table, no CRUD entry.
Future<void> syncedNotice(PowerSyncDatabase raw, String id, String createdAt) => raw.execute(
      'INSERT INTO ps_data__notices (id, data) VALUES (?, ?)',
      [
        id,
        jsonEncode({
          'user_id': 'user-1',
          'kind': 'task_due',
          'title': 'T $id',
          'body': 'b',
          'data': jsonEncode({'task_id': 'task-1', 'stage': 'due', 'actions': ['done']}),
          'created_at': createdAt,
          'read_at': null,
          'dismissed_at': null,
        }),
      ],
    );

void main() {
  late Directory dir;
  late PowerSyncDatabase raw;
  late SyncDb db;

  setUp(() async {
    clock = DateTime.utc(2026, 11, 12, 15);
    dir = Directory.systemTemp.createTempSync('bnp_real');
    raw = PowerSyncDatabase(schema: _schema, path: '${dir.path}/t.db');
    await raw.initialize();
    db = PowerSyncDb(raw);
  });

  tearDown(() async {
    await raw.close();
    dir.deleteSync(recursive: true);
  });

  test('notice feed order, markRead and dismiss are patches of one column', () async {
    await syncedNotice(raw, 'n1', '2026-11-12T10:00:00Z');
    await syncedNotice(raw, 'n2', '2026-11-12T12:00:00Z');
    await syncedNotice(raw, 'n3', '2026-11-12T11:00:00');
    final feed = WatchNoticeFeed(db, userId: 'user-1', now: () => clock);
    final seen = <List<String>>[];
    final sub = feed.watch().listen((l) => seen.add([for (final n in l) n.id]));
    await Future<void>.delayed(const Duration(milliseconds: 150));
    expect(seen.last, ['n2', 'n3', 'n1']);
    expect((await feed.watch().first).first.taskId, 'task-1');

    await feed.markRead('n2');
    await feed.dismiss('n3');
    await Future<void>.delayed(const Duration(milliseconds: 150));
    await sub.cancel();
    expect(seen.last, ['n2', 'n1']);

    final entries = await drain(db);
    expect(entries.map((e) => (e.op, e.table, e.id)), [('patch', 'notices', 'n2'), ('patch', 'notices', 'n3')]);
    expect(entries[0].opData, {'read_at': '2026-11-12T15:00:00.000Z'});
    expect(entries[1].opData, {'dismissed_at': '2026-11-12T15:00:00.000Z'});
  });

  test('markAllRead queues one patch per unread row, each with only read_at', () async {
    await syncedNotice(raw, 'n1', '2026-11-12T10:00:00Z');
    await syncedNotice(raw, 'n2', '2026-11-12T12:00:00Z');
    await syncedNotice(raw, 'n3', '2026-11-12T11:00:00Z');
    await syncedNotice(raw, 'n4', '2026-11-12T13:00:00Z');
    final feed = WatchNoticeFeed(db, userId: 'user-1', now: () => clock);
    await feed.dismiss('n3');
    await feed.markRead('n1');
    await drain(db);
    await feed.markAllRead();
    final entries = await drain(db);
    expect(entries.map((e) => (e.op, e.table, e.id)), [('patch', 'notices', 'n2'), ('patch', 'notices', 'n4')]);
    for (final e in entries) {
      expect(e.opData, {'read_at': '2026-11-12T15:00:00.000Z'});
    }
    expect(await raw.getAll('SELECT id FROM notices WHERE read_at IS NULL AND dismissed_at IS NULL'), isEmpty);
  });

  test('devices: register twice is one put then one patch; unregister is a delete', () async {
    final devices = SyncPushDevices(db, userId: 'user-1', now: () => clock);
    await devices.register(const PushToken(value: 'tok1', environment: 'sandbox'), deviceId: 'dev1', topic: 'com.example.app');
    clock = clock.add(const Duration(hours: 1));
    await devices.register(const PushToken(value: 'tok2', environment: 'production'), deviceId: 'dev1', topic: 'com.example.app');
    final id = devices.rowId('dev1');
    expect(await raw.getAll('SELECT id, token FROM push_devices'), [
      {'id': id, 'token': 'tok2'},
    ]);
    await devices.unregister('dev1');
    expect(await raw.getAll('SELECT id FROM push_devices'), isEmpty);

    final entries = await drain(db);
    expect(entries.map((e) => (e.op, e.table, e.id)), [
      ('put', 'push_devices', id),
      ('patch', 'push_devices', id),
      ('delete', 'push_devices', id),
    ]);
    expect(entries[0].opData, containsPair('token', 'tok1'));
    expect(entries[0].opData, containsPair('device_id', 'dev1'));
    // a debug build to a release build: token and environment change, nothing server-owned is written
    expect(entries[1].opData, {'token': 'tok2', 'environment': 'production'});
  });
}
