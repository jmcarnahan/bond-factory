@Tags(['real_db'])
@TestOn('vm')
library;

/// The fixture `fixtures/legacy_host/upload_push_devices.json` is what the phone queues: a REAL local PowerSync
/// database runs `SyncPushDevices.register` / `unregister`, and the queued CRUD entries must equal the fixture's ops
/// (op, table, id, and the exact data keys and values). The legacy host replays the same file.
import 'dart:convert';
import 'dart:io';

import 'package:bond_notify_powersync/bond_notify_powersync.dart';
import 'package:bond_push/bond_push.dart';
import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:powersync/powersync.dart';

final _schema = Schema([...pushDevicesTables(), ...syncSupportTables()]);

List<Map<String, Object?>> fixtureOps() {
  final json = jsonDecode(File('../../fixtures/legacy_host/upload_push_devices.json').readAsStringSync()) as Map;
  return [
    for (final r in json['requests'] as List)
      for (final op in ((r as Map)['body'] as Map)['ops'] as List) (op as Map).cast<String, Object?>(),
  ];
}

void main() {
  test('register, token refresh and unregister queue exactly the fixture ops', () async {
    final dir = Directory.systemTemp.createTempSync('bnp_upload');
    final raw = PowerSyncDatabase(schema: _schema, path: '${dir.path}/t.db');
    addTearDown(() async {
      await raw.close();
      dir.deleteSync(recursive: true);
    });
    await raw.initialize();
    final db = PowerSyncDb(raw);

    final devices = SyncPushDevices(db, userId: 'u-owner', now: () => DateTime.utc(2026, 11, 12, 15));
    await devices.register(PushToken(value: 'a' * 64, environment: 'sandbox'), deviceId: 'device-1', topic: 'com.example.app');
    await devices.register(PushToken(value: 'b' * 64, environment: 'sandbox'), deviceId: 'device-1', topic: 'com.example.app');
    await devices.unregister('device-1');

    final queued = <SyncCrudEntry>[];
    while (true) {
      final tx = await db.nextCrudTransaction();
      if (tx == null) break;
      queued.addAll(tx.entries);
      await tx.complete();
    }
    final expected = fixtureOps();
    expect(queued, hasLength(expected.length));
    for (var i = 0; i < expected.length; i++) {
      final want = expected[i];
      expect(queued[i].op, want['op'], reason: 'op $i');
      expect(queued[i].table, want['table'], reason: 'table $i');
      expect(queued[i].id, want['id'], reason: 'id $i');
      expect(queued[i].opData, want['data'], reason: 'data $i'); // null for a delete on both sides
    }
    expect(devices.rowId('device-1'), expected.first['id']);
  });
}
