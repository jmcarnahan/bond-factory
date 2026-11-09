import 'dart:io';

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:powersync/powersync.dart';

import 'fake_sync_db.dart';

final _schema = Schema([
  const Table('notes', [Column.text('title')]),
  const Table('files', [Column.text('path')]),
  ...syncSupportTables(),
]);

void main() {
  group('SyncPolicy', () {
    test('synced tables exclude the local-only support tables', () {
      final p = SyncPolicy(schema: _schema);
      expect(p.schemaTables, {'notes', 'files'});
      expect(syncSupportTables().map((t) => t.name), ['sync_rejections', 'sync_meta']);
      expect(syncSupportTables().every((t) => t.localOnly), isTrue);
    });

    test('sendable tables drop the not-uploaded ones', () {
      expect(SyncPolicy(schema: _schema, notUploadedTables: const {'files'}).sendableTables, {'notes'});
    });

    test('defaults are the contract numbers and map onto the limits', () {
      final p = SyncPolicy(schema: _schema);
      expect(p.chunkSize, 100);
      expect(p.chunkBytes, 512 * 1024);
      expect(p.transientMaxCount, 8);
      expect(p.transientMaxSpan, const Duration(minutes: 15));
      expect(p.transientStale, const Duration(minutes: 10));
      final l = SyncPolicy(schema: _schema, chunkSize: 5, sendCaps: const {'notes:': 2}, transientMaxCount: 3).limits;
      expect(l.chunkSize, 5);
      expect(l.sendCaps, {'notes:': 2});
      expect(l.transientMaxCount, 3);
    });

    test('silent writes honour the action set', () {
      final p = SyncPolicy(schema: _schema, silentWrites: const {'notes': {'read'}, 'files': null});
      expect(p.isSilentWrite(table: 'notes', action: 'read'), isTrue);
      expect(p.isSilentWrite(table: 'notes', action: 'other'), isFalse);
      expect(p.isSilentWrite(table: 'notes'), isFalse);
      expect(p.isSilentWrite(table: 'files'), isTrue);
    });
  });

  test('syncDbPath and BondSyncNames come through the barrel', () {
    expect(syncDbPath('/d', 'u@x', prefix: 'app'), '/d/app_u_x.db');
    expect(const BondSyncNames().loggerName, 'bond.sync');
  });

  group('openSyncStore', () {
    late Directory dir;
    setUp(() => dir = Directory.systemTemp.createTempSync('bond_sync_open_'));
    tearDown(() => dir.deleteSync(recursive: true));

    Future<SyncStoreOpen> open(List<FakeSyncDb> made, {int failuresEach = 0, String? path}) => openSyncStore(
          policy: SyncPolicy(schema: _schema),
          path: path ?? '${dir.path}/bond_u1.db',
          retryDelay: Duration.zero,
          now: () => DateTime.utc(2026, 11, 8, 10),
          dbFactory: (schema, p) {
            final d = FakeSyncDb()..initFailures = failuresEach;
            made.add(d);
            return d;
          },
        );

    test('opens on the first try and prunes old notes', () async {
      final made = <FakeSyncDb>[];
      final o = await open(made);
      expect(made, hasLength(1));
      expect(o.movedAside, isFalse);
      expect(o.powerSync, isNull);
      expect(made.single.where('DELETE FROM sync_rejections'), hasLength(1));
    });

    test('a failure is retried on the same files', () async {
      final made = <FakeSyncDb>[];
      var n = 0;
      final o = await openSyncStore(
        policy: SyncPolicy(schema: _schema),
        path: '${dir.path}/bond_u1.db',
        retryDelay: Duration.zero,
        dbFactory: (s, p) {
          final d = FakeSyncDb()..initFailures = n++ == 0 ? 1 : 0;
          made.add(d);
          return d;
        },
      );
      expect(made, hasLength(2));
      expect(made.first.closes, 1);
      expect(made.first.disconnects, 1);
      expect(o.movedAside, isFalse);
    });

    test('two failures move the files aside, never delete, and record the reset', () async {
      File('${dir.path}/bond_u1.db').writeAsStringSync('queued writes');
      File('${dir.path}/bond_u1.db-wal').writeAsStringSync('wal');
      final made = <FakeSyncDb>[];
      var n = 0;
      final o = await openSyncStore(
        policy: SyncPolicy(schema: _schema),
        path: '${dir.path}/bond_u1.db',
        retryDelay: Duration.zero,
        now: () => DateTime.utc(2026, 11, 8, 10),
        dbFactory: (s, p) {
          final d = FakeSyncDb()..initFailures = n++ < 2 ? 1 : 0;
          made.add(d);
          return d;
        },
      );
      expect(made, hasLength(3));
      expect(o.movedAside, isTrue);
      final names = dir.listSync().map((e) => e.uri.pathSegments.last).toList()..sort();
      final stamp = DateTime.utc(2026, 11, 8, 10).millisecondsSinceEpoch;
      expect(names, ['bond_u1.db-wal.bad-$stamp', 'bond_u1.db.bad-$stamp']);
      expect(File('${dir.path}/bond_u1.db.bad-$stamp').readAsStringSync(), 'queued writes');
      expect(made.last.where('INSERT OR REPLACE INTO sync_meta').single.params.first, kSyncStoreResetKey);
    });

    test('three failures throw SyncOpenFailure', () async {
      final made = <FakeSyncDb>[];
      await expectLater(open(made, failuresEach: 1), throwsA(isA<SyncOpenFailure>()));
      expect(made, hasLength(3));
      expect(made.every((d) => d.closes == 1), isTrue);
    });

    test('older moved-aside copies are deleted after a new one is made', () async {
      File('${dir.path}/bond_u1.db').writeAsStringSync('x');
      File('${dir.path}/bond_u1.db.bad-1').writeAsStringSync('old');
      final opener = SyncStoreOpener(policy: SyncPolicy(schema: _schema), now: () => DateTime.utc(2026));
      final moved = opener.moveAside('${dir.path}/bond_u1.db');
      expect(moved, hasLength(1));
      expect(File('${dir.path}/bond_u1.db.bad-1').existsSync(), isFalse);
    });

    test('deleteStoreFiles removes the file, siblings and copies', () {
      for (final s in ['', '-wal', '-shm', '.bad-5']) {
        File('${dir.path}/bond_u1.db$s').writeAsStringSync('x');
      }
      File('${dir.path}/other.db').writeAsStringSync('x');
      deleteStoreFiles('${dir.path}/bond_u1.db');
      expect(dir.listSync().map((e) => e.uri.pathSegments.last), ['other.db']);
    });
  });
}
