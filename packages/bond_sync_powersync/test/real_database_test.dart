@Tags(['real_db'])
@TestOn('vm')
library;

import 'dart:io';

import 'package:bond_sync/bond_sync.dart';
import 'package:bond_sync/testing.dart';
import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:powersync/powersync.dart';

/// Runs the adapter against a REAL PowerSync database (the core extension is
/// fetched by powersync's build hook). No sync service: only the local CRUD
/// queue, which is what `SyncConnector.uploadData` reads.
final _schema = Schema([
  const Table('notes', [Column.text('title')]),
  ...syncSupportTables(),
]);

void main() {
  late Directory dir;
  late PowerSyncDatabase db;
  late PowerSyncSyncStore store;
  late SyncPolicy policy;

  setUp(() async {
    dir = Directory.systemTemp.createTempSync('bsp_real');
    policy = SyncPolicy(schema: _schema, createPuts: const {'notes': null});
    db = PowerSyncDatabase(schema: _schema, path: '${dir.path}/t.db');
    await db.initialize();
    store = PowerSyncSyncStore(db, policy: policy);
  });

  tearDown(() async {
    await db.close();
    dir.deleteSync(recursive: true);
  });

  Future<void> writeTwo() => db.writeTransaction((tx) async {
        await tx.execute('INSERT INTO notes (id, title) VALUES (?, ?)', ['n1', 'kept']);
        await tx.execute('INSERT INTO notes (id, title) VALUES (?, ?)', ['n2', 'refused']);
      });

  test('the store reads the real CRUD batch', () async {
    await writeTwo();
    final batch = await store.nextBatch();
    expect(batch, isNotNull);
    expect(batch!.ops.map((o) => (o.table, o.id, o.op)), [('notes', 'n1', 'put'), ('notes', 'n2', 'put')]);
    expect(batch.ops.first.data['title'], 'kept');
  });

  test('uploadData drains the queue and records the rejection', () async {
    await writeTwo();
    final transport = FakeSyncTransport()
      ..enqueueUpload(
        const UploadResponse(results: [
          SyncOpResult(seq: 0, status: 'ok'),
          SyncOpResult(seq: 1, status: 'rejected', code: 'invalid', message: 'Bad title'),
        ]),
      );
    final connector = SyncConnector(
      transport: transport,
      clock: ServerClock(() => DateTime.utc(2026, 11, 8, 10)),
      policy: policy,
    );

    await connector.uploadData(db);

    expect(transport.uploads, hasLength(1));
    expect(transport.uploads.single.ops, hasLength(2));
    expect(await db.getNextCrudTransaction(), isNull, reason: 'the CRUD queue drained');

    final notes = await store.rejections();
    expect(notes, hasLength(1));
    expect(notes.single.rowId, 'n2');
    expect(notes.single.code, 'invalid');

    // The refused create removed its optimistic row; the accepted one stays.
    final titles = [for (final r in await store.rows('notes')) r['title']];
    expect(titles, ['kept']);
  });
}
