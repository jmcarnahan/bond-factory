@Tags(['real_db'])
@TestOn('vm')
library;

/// An app may leave `token` out of the `push_devices` stream (a token is a send capability, and no Dart class reads it
/// back). After a sync the local row's `token` then reads NULL. `SyncPushDevices.register` must still work: it never
/// reads the token, it writes it.
import 'dart:convert';
import 'dart:io';

import 'package:bond_notify_powersync/bond_notify_powersync.dart';
import 'package:bond_push/bond_push.dart';
import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:powersync/powersync.dart';

final _schema = Schema([...pushDevicesTables(), ...syncSupportTables()]);

void main() {
  late Directory dir;
  late PowerSyncDatabase raw;
  late SyncDb db;
  late SyncPushDevices devices;

  setUp(() async {
    dir = Directory.systemTemp.createTempSync('bnp_notoken');
    raw = PowerSyncDatabase(schema: _schema, path: '${dir.path}/t.db');
    await raw.initialize();
    db = PowerSyncDb(raw);
    devices = SyncPushDevices(db, userId: 'u-owner', now: () => DateTime.utc(2026, 11, 12, 15));
    // a downloaded row, as the sync client writes it: no CRUD entry, and no `token` key (the stream omits it)
    await raw.execute('INSERT INTO ps_data__push_devices (id, data) VALUES (?, ?)', [
      devices.rowId('device-1'),
      jsonEncode({
        'user_id': 'u-owner',
        'device_id': 'device-1',
        'platform': 'ios',
        'environment': 'sandbox',
        'topic': 'com.example.app',
        'last_seen_at': '2026-11-01T00:00:00.000Z',
        'created_at': '2026-11-01T00:00:00.000Z',
      }),
    ]);
  });

  tearDown(() async {
    await raw.close();
    dir.deleteSync(recursive: true);
  });

  Future<List<SyncCrudEntry>> drain() async {
    final out = <SyncCrudEntry>[];
    while (true) {
      final tx = await db.nextCrudTransaction();
      if (tx == null) return out;
      out.addAll(tx.entries);
      await tx.complete();
    }
  }

  test('the local token reads NULL', () async {
    final row = await raw.get('SELECT token FROM push_devices');
    expect(row['token'], isNull);
  });

  test('register after such a sync updates the row and queues a patch carrying the token', () async {
    await devices.register(PushToken(value: 'a' * 64, environment: 'sandbox'), deviceId: 'device-1', topic: 'com.example.app');
    expect(await raw.getAll('SELECT id, token FROM push_devices'), [
      {'id': devices.rowId('device-1'), 'token': 'a' * 64},
    ]);
    final entries = await drain();
    expect(entries.map((e) => (e.op, e.table, e.id)), [('patch', 'push_devices', devices.rowId('device-1'))]);
    expect(entries.single.opData, {'token': 'a' * 64});
  });

  test('register on a device the sync never delivered inserts', () async {
    await devices.register(PushToken(value: 'b' * 64, environment: 'sandbox'), deviceId: 'device-2');
    final entries = await drain();
    expect(entries.single.op, 'put');
    expect(entries.single.opData?['token'], 'b' * 64);
  });
}
